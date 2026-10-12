from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user
from ..models import ApiToken, User
from ..ratelimit import client_ip, limiter
from ..schemas import (ApiTokenCreated, ApiTokenIn, ApiTokenOut, LoginIn, RegisterIn, SettingsIn, TokenOut,
                       UserOut)
from ..security import create_access_token, hash_password, new_api_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"register:{client_ip(request)}", 5, 3600)
    if not body.accept_terms:
        raise HTTPException(400, "You must accept the responsible-use terms")
    if body.password.lower() in body.email.lower() or len(set(body.password)) < 5:
        raise HTTPException(400, "Choose a stronger password")
    first = db.scalar(select(func.count(User.id))) == 0
    user = User(email=body.email.lower(), password_hash=hash_password(body.password),
                role="admin" if first else "analyst")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists")
    audit(db, "auth.register", user_id=user.id, request=request, detail={"role": user.role})
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"login:{client_ip(request)}", 10, 60)
    limiter.check(f"login-acct:{body.email.lower()}", 20, 900)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        audit(db, "auth.login_failed", user_id=user.id if user else None, request=request)
        raise HTTPException(401, "Incorrect email or password")
    audit(db, "auth.login", user_id=user.id, request=request)
    return TokenOut(access_token=create_access_token(user.id), expires_in=get_settings().access_token_minutes * 60)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me/settings", response_model=UserOut)
def update_settings(body: SettingsIn, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if body.alert_threshold is not None:
        user.alert_threshold = body.alert_threshold
    if body.email_alerts is not None:
        user.email_alerts = body.email_alerts
    audit(db, "user.settings", user_id=user.id, request=request, detail=body.model_dump(exclude_none=True))
    return user


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
