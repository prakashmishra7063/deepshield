from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .billing import verification_enforced
from .config import get_settings
from .db import get_db
from .models import ApiToken, Membership, Organization, User, utcnow
from .ratelimit import limiter
from .security import API_TOKEN_PREFIX, decode_access_token, hash_api_token

bearer = HTTPBearer(auto_error=False)
ORG_ROLE_RANK = {"member": 0, "admin": 1, "owner": 2}


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    raw = creds.credentials
    user: User | None = None
    if raw.startswith(API_TOKEN_PREFIX):
        tok = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_api_token(raw), ApiToken.revoked.is_(False)))
        if tok:
            tok.last_used_at = utcnow()
            db.commit()
            user = tok.user
            request.state.via_api_token = True
    else:
        decoded = decode_access_token(raw)
        if decoded is not None:
            candidate = db.get(User, decoded[0])
            if candidate and candidate.token_version == decoded[1]:
                user = candidate
    if not user:
        raise HTTPException(401, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"})
    if user.status != "active":
        raise HTTPException(403, "This account is suspended. Contact support.")
    limiter.check(f"user:{user.id}", get_settings().rate_limit_per_minute * 2, 60)
    return user


@dataclass
class Ctx:
    """The signed-in user acting inside their active workspace."""
    user: User
    org: Organization
    role: str  # owner | admin | member

    @property
    def is_admin(self) -> bool:
        return ORG_ROLE_RANK[self.role] >= ORG_ROLE_RANK["admin"]


def ensure_personal_org(db: Session, user: User) -> Organization:
    org = Organization(name=f"{user.email.split('@')[0]}'s workspace", kind="personal",
                       plan_id="internal" if user.role == "owner" else "free", created_by=user.id)
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    user.active_org_id = org.id
    db.commit()
    return org


def get_ctx(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Ctx:
    m = None
    if user.active_org_id:
        m = db.get(Membership, (user.active_org_id, user.id))
    if m is None:
        m = db.scalars(select(Membership).where(Membership.user_id == user.id)
                       .order_by(Membership.created_at)).first()
        if m is None:
            ensure_personal_org(db, user)
            m = db.get(Membership, (user.active_org_id, user.id))
        user.active_org_id = m.org_id
        db.commit()
    return Ctx(user=user, org=m.org, role=m.role)


def require_org_admin(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    if not ctx.is_admin:
        raise HTTPException(403, "Only workspace admins can do this")
    return ctx


def require_verified(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)) -> Ctx:
    if verification_enforced(db) and not ctx.user.email_verified_at:
        raise HTTPException(403, "Please verify your email address before scanning. Check your inbox or resend the "
                                 "verification email from the banner.")
    return ctx


def require_platform_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(403, "Platform owner access required")
    return user


# Backwards-compatible name used by older routes.
require_admin = require_platform_owner
