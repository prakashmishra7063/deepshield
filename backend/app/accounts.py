"""Account lifecycle: signup, emailed tokens, invites and safe deletion."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import mailer, storage
from .config import get_settings
from .deps import ensure_personal_org
from .models import (Analysis, ApiToken, Case, CaseNote, EmailToken, Invite, MediaObject, Membership, Organization,
                     User, utcnow)
from .security import hash_password, hash_secret_token, new_secret_token


def as_aware(dt):
    from datetime import timezone
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


# ---------------------------------------------------------------- signup

def create_user(db: Session, email: str, password: str) -> User:
    first = db.scalar(select(func.count(User.id))) == 0
    user = User(email=email.lower(), password_hash=hash_password(password), role="owner" if first else "user",
                email_verified_at=utcnow() if first else None)
    db.add(user)
    db.flush()
    ensure_personal_org(db, user)
    return user


# ---------------------------------------------------------------- email tokens

def _issue(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    # Invalidate earlier unused tokens for the same purpose.
    for t in db.scalars(select(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == purpose,
                                                 EmailToken.used_at.is_(None))):
        t.used_at = utcnow()
    raw, digest = new_secret_token()
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=digest, expires_at=utcnow() + ttl))
    db.commit()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> User:
    t = db.scalar(select(EmailToken).where(EmailToken.token_hash == hash_secret_token(raw),
                                           EmailToken.purpose == purpose))
    if not t or t.used_at or as_aware(t.expires_at) < utcnow():
        raise HTTPException(400, "This link is invalid or has expired. Request a new one.")
    t.used_at = utcnow()
    user = db.get(User, t.user_id)
    if not user:
        raise HTTPException(400, "This link is invalid or has expired.")
    return user


def send_verification(db: Session, user: User) -> mailer.SendResult:
    s = get_settings()
    raw = _issue(db, user, "verify", timedelta(hours=s.verification_hours))
    return mailer.send(user.email, "Verify your email address",
                f"Welcome to {s.product_name}!\n\nConfirm your email address to start scanning:\n"
                f"{mailer.link('/verify-email?token=' + raw)}\n\nThis link expires in {s.verification_hours} hours. "
                "If you didn't create an account, you can ignore this email.")


def send_password_reset(db: Session, user: User) -> mailer.SendResult:
    s = get_settings()
    raw = _issue(db, user, "reset", timedelta(minutes=s.reset_minutes))
    return mailer.send(user.email, "Reset your password",
                f"Someone (hopefully you) asked to reset your {s.product_name} password.\n\n"
                f"Choose a new password here:\n{mailer.link('/reset-password?token=' + raw)}\n\n"
                f"This link expires in {s.reset_minutes} minutes. If you didn't ask for this, ignore this email; "
                "your password won't change.")


def revoke_sessions(db: Session, user: User, include_api_tokens: bool = True) -> None:
    user.token_version += 1
    if include_api_tokens:
        for t in db.scalars(select(ApiToken).where(ApiToken.user_id == user.id)):
            t.revoked = True


# ---------------------------------------------------------------- invites

def create_invite(db: Session, org: Organization, inviter: User, email: str, role: str) -> Invite:
    """Create and email an invitation; nothing is kept if the email can't be sent."""
    s = get_settings()
    raw, digest = new_secret_token()
    inv = Invite(org_id=org.id, email=email.lower(), role=role, token_hash=digest, invited_by=inviter.id,
                 expires_at=utcnow() + timedelta(days=s.invite_days))
    db.add(inv)
    db.commit()
    sent = mailer.send(email, f"You're invited to {org.name}",
                       f"{inviter.email} invited you to join the '{org.name}' workspace on {s.product_name}.\n\n"
                       f"Accept the invitation:\n{mailer.link('/invite?token=' + raw)}\n\n"
                       f"The invitation expires in {s.invite_days} days.")
    if not sent.ok:
        db.delete(inv)
        db.commit()
        raise HTTPException(502, f"The invitation email could not be sent. {sent.error or ''}".strip())
    return inv


def find_invite(db: Session, raw: str) -> Invite:
    inv = db.scalar(select(Invite).where(Invite.token_hash == hash_secret_token(raw)))
    if not inv or inv.accepted_at or as_aware(inv.expires_at) < utcnow():
        raise HTTPException(400, "This invitation is invalid, expired or already used.")
    return inv


def accept_invite(db: Session, inv: Invite, user: User) -> Membership:
    if inv.email != user.email:
        raise HTTPException(403, f"This invitation was sent to {inv.email}. Sign in with that address to accept it.")
    m = db.get(Membership, (inv.org_id, user.id))
    if not m:
        if seats_used(db, inv.org, exclude_invite=inv.id) >= inv.org.plan.max_members:
            raise HTTPException(402, "This workspace has no free seats. Ask its admin to upgrade the plan.")
        m = Membership(org_id=inv.org_id, user_id=user.id, role=inv.role)
        db.add(m)
    inv.accepted_at = utcnow()
    user.active_org_id = inv.org_id
    # Accepting an emailed invite proves control of the address.
    if not user.email_verified_at:
        user.email_verified_at = utcnow()
    db.commit()
    return m


def seats_used(db: Session, org: Organization, exclude_invite: int | None = None) -> int:
    members = db.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == org.id))
    pending = db.scalar(select(func.count(Invite.id)).where(
        Invite.org_id == org.id, Invite.accepted_at.is_(None), Invite.expires_at > utcnow(),
        Invite.id != (exclude_invite or -1)))
    return (members or 0) + (pending or 0)


# ---------------------------------------------------------------- deletion

def delete_org(db: Session, org: Organization) -> None:
    """Delete a workspace with all of its analyses, stored media and evidence."""
    analyses = db.scalars(select(Analysis).where(Analysis.org_id == org.id)).all()
    media_ids = {a.media_id for a in analyses if a.media_id}
    for a in analyses:
        storage.delete_derived(a.id)
        db.delete(a)
    db.flush()
    for mid in media_ids:
        m = db.get(MediaObject, mid)
        if m and not db.scalar(select(func.count(Analysis.id)).where(Analysis.media_id == mid)):
            storage.delete_original(m.storage_path)
            db.delete(m)
    for u in db.scalars(select(User).where(User.active_org_id == org.id)):
        u.active_org_id = None
    db.delete(org)
    db.flush()


def delete_user(db: Session, user: User) -> None:
    """Delete an account. Personal workspaces go with it; team workspaces it solely owns are
    handed to the longest-standing remaining member, or deleted if nobody is left."""
    for m in db.scalars(select(Membership).where(Membership.user_id == user.id)).all():
        org = m.org
        others = [x for x in org.members if x.user_id != user.id]
        if org.kind == "personal" or not others:
            delete_org(db, org)
            continue
        if m.role == "owner" and not any(x.role == "owner" for x in others):
            heir = sorted(others, key=lambda x: (-{"admin": 1, "member": 0}.get(x.role, 0), x.created_at))[0]
            heir.role = "owner"
    db.flush()
    # Keep team data that this user created; just detach the authorship.
    for model in (Analysis, Case, CaseNote):
        db.execute(update(model).where(model.user_id == user.id).values(user_id=None))
    db.delete(user)
    db.commit()


def last_owner(db: Session, org: Organization, user_id: int) -> bool:
    owners = [m for m in org.members if m.role == "owner"]
    return len(owners) == 1 and owners[0].user_id == user_id
