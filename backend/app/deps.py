from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import ApiToken, User, utcnow
from .ratelimit import limiter
from .security import API_TOKEN_PREFIX, decode_access_token, hash_api_token

bearer = HTTPBearer(auto_error=False)


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
        uid = decode_access_token(raw)
        if uid is not None:
            user = db.get(User, uid)
    if not user:
        raise HTTPException(401, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"})
    limiter.check(f"user:{user.id}", get_settings().rate_limit_per_minute * 2, 60)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return user
