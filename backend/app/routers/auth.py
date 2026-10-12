from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import accounts, mailer
from ..audit import audit
from ..billing import setting
from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user
from ..models import ApiToken, Membership, User, utcnow
from ..ratelimit import client_ip, limiter
from ..schemas import (ApiTokenCreated, ApiTokenIn, ApiTokenOut, ChangePasswordIn, DeleteAccountIn, EmailIn, LoginIn,
                       MeOut, MembershipOut, RegisterIn, ResetIn, SettingsIn, SwitchOrgIn, TokenIn, TokenOut)
from ..security import create_access_token, hash_password, new_api_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _check_password_strength(password: str, email: str) -> None:
    if password.lower() in email.lower() or len(set(password)) < 5:
        raise HTTPException(400, "Choose a stronger password")


def me_out(db: Session, user: User) -> MeOut:
    ms = db.scalars(select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)).all()
    return MeOut(id=user.id, email=user.email, role=user.role, status=user.status,
                 email_verified=user.email_verified_at is not None, alert_threshold=user.alert_threshold,
                 email_alerts=user.email_alerts, created_at=user.created_at, active_org_id=user.active_org_id,
                 memberships=[MembershipOut(org_id=m.org_id, name=m.org.name, kind=m.org.kind, role=m.role,
                                            plan_id=m.org.plan_id) for m in ms],
                 require_email_verification=bool(setting(db, "require_email_verification")),
                 email_delivery=mailer.delivery_mode())


@router.post("/register", response_model=MeOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"register:{client_ip(request)}", 5, 3600)
    if not body.accept_terms:
        raise HTTPException(400, "You must accept the terms and responsible-use policy")
    invite = accounts.find_invite(db, body.invite_token) if body.invite_token else None
    if invite and invite.email != body.email.lower():
        raise HTTPException(403, f"This invitation was sent to {invite.email}. Register with that address.")
    first = db.scalar(select(func.count(User.id))) == 0
    if not first and not invite and not setting(db, "signups_open"):
        raise HTTPException(403, "New sign-ups are currently closed.")
    _check_password_strength(body.password, body.email)
    try:
        user = accounts.create_user(db, body.email, body.password)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists")
    if invite:
        accounts.accept_invite(db, invite, user)
    elif not user.email_verified_at:
        accounts.send_verification(db, user)
    audit(db, "auth.register", user_id=user.id, request=request, detail={"role": user.role, "invited": bool(invite)})
    return me_out(db, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"login:{client_ip(request)}", 10, 60)
    limiter.check(f"login-acct:{body.email.lower()}", 20, 900)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        audit(db, "auth.login_failed", user_id=user.id if user else None, request=request)
        raise HTTPException(401, "Incorrect email or password")
    if user.status != "active":
        audit(db, "auth.login_suspended", user_id=user.id, request=request)
        raise HTTPException(403, "This account is suspended. Contact support.")
    user.last_login_at = utcnow()
    audit(db, "auth.login", user_id=user.id, request=request)
    return TokenOut(access_token=create_access_token(user.id, user.token_version),
                    expires_in=get_settings().access_token_minutes * 60)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return me_out(db, user)


@router.patch("/me/settings", response_model=MeOut)
def update_settings(body: SettingsIn, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if body.alert_threshold is not None:
        user.alert_threshold = body.alert_threshold
    if body.email_alerts is not None:
        user.email_alerts = body.email_alerts
    audit(db, "user.settings", user_id=user.id, request=request, detail=body.model_dump(exclude_none=True))
    return me_out(db, user)


# ---------------------------------------------------------------- email verification & passwords

@router.post("/verify-email", response_model=MeOut)
def verify_email(body: TokenIn, request: Request, db: Session = Depends(get_db)):
    user = accounts.consume_token(db, body.token, "verify")
    user.email_verified_at = user.email_verified_at or utcnow()
    audit(db, "auth.email_verified", user_id=user.id, request=request)
    return me_out(db, user)


@router.post("/resend-verification", status_code=204)
def resend_verification(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    limiter.check(f"verify-mail:{user.id}", 3, 3600)
    if not user.email_verified_at:
        sent = accounts.send_verification(db, user)
        if not sent.ok:
            raise HTTPException(502, f"The verification email could not be sent. {sent.error or ''}".strip())


@router.post("/forgot-password", status_code=204)
def forgot_password(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    """Always succeeds so the endpoint can't be used to discover which emails have accounts."""
    limiter.check(f"forgot:{client_ip(request)}", 5, 3600)
    limiter.check(f"forgot-acct:{body.email.lower()}", 3, 3600)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.status == "active":
        accounts.send_password_reset(db, user)
        audit(db, "auth.reset_requested", user_id=user.id, request=request)


@router.post("/reset-password", status_code=204)
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"reset:{client_ip(request)}", 10, 3600)
    user = accounts.consume_token(db, body.token, "reset")
    _check_password_strength(body.password, user.email)
    user.password_hash = hash_password(body.password)
    user.email_verified_at = user.email_verified_at or utcnow()  # the reset link proved inbox access
    accounts.revoke_sessions(db, user, include_api_tokens=False)
    audit(db, "auth.password_reset", user_id=user.id, request=request)


@router.post("/change-password", response_model=TokenOut)
def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Your current password is incorrect")
    _check_password_strength(body.new_password, user.email)
    user.password_hash = hash_password(body.new_password)
    accounts.revoke_sessions(db, user, include_api_tokens=False)  # signs out other sessions
    audit(db, "auth.password_changed", user_id=user.id, request=request)
    return TokenOut(access_token=create_access_token(user.id, user.token_version),
                    expires_in=get_settings().access_token_minutes * 60)


@router.post("/logout-everywhere", status_code=204)
def logout_everywhere(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts.revoke_sessions(db, user, include_api_tokens=False)
    audit(db, "auth.logout_everywhere", user_id=user.id, request=request)


@router.delete("/me", status_code=204)
def delete_account(body: DeleteAccountIn, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "Password is incorrect")
    if user.role == "owner" and db.scalar(select(func.count(User.id)).where(User.role == "owner")) == 1:
        raise HTTPException(409, "You are the only platform owner. Make another user owner before deleting this account.")
    uid, email = user.id, user.email
    accounts.delete_user(db, user)
    audit(db, "auth.account_deleted", user_id=None, target=str(uid), request=request, detail={"email": email})


@router.post("/switch-org", response_model=MeOut)
def switch_org(body: SwitchOrgIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Membership, (body.org_id, user.id)):
        raise HTTPException(404, "Workspace not found")
    user.active_org_id = body.org_id
    db.commit()
    return me_out(db, user)


# ---------------------------------------------------------------- API tokens

@router.get("/tokens", response_model=list[ApiTokenOut])
def list_tokens(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())).all()


@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
def create_token(body: ApiTokenIn, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if getattr(request.state, "via_api_token", False):
        raise HTTPException(403, "API tokens cannot mint new tokens")
    active = db.scalar(select(func.count(ApiToken.id)).where(ApiToken.user_id == user.id, ApiToken.revoked.is_(False)))
    if active >= 10:
        raise HTTPException(400, "Token limit reached. Revoke an existing token first.")
    raw, digest = new_api_token()
    tok = ApiToken(user_id=user.id, name=body.name, token_hash=digest, prefix=raw[:10])
    db.add(tok)
    db.commit()
    audit(db, "token.create", user_id=user.id, target=str(tok.id), request=request)
    return ApiTokenCreated(**ApiTokenOut.model_validate(tok).model_dump(), token=raw)


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    tok = db.get(ApiToken, token_id)
    if not tok or tok.user_id != user.id:
        raise HTTPException(404, "Token not found")
    tok.revoked = True
    db.commit()
    audit(db, "token.revoke", user_id=user.id, target=str(token_id), request=request)
