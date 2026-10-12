"""Platform owner console. Returns account and usage *metadata* only: the owner can
manage customers, workspaces, plans and credits, but cannot open customers' media,
results or notes through these endpoints."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import accounts, mailer
from ..audit import audit
from ..billing import month_start, setting, usage
from ..db import get_db
from ..deps import require_platform_owner
from ..models import Analysis, AuditLog, Membership, Organization, Plan, PlatformSetting, User, utcnow
from ..schemas import (AdminOrgOut, AdminOrgPatch, AdminUserOut, AdminUserPatch, AuditOut, PlanIn, PlanOut,
                       PlanPatch, PlatformSettingsIO)

router = APIRouter(prefix="/admin", tags=["owner console"])


@router.get("/overview")
def overview(_: User = Depends(require_platform_owner), db: Session = Depends(get_db)):
    start = month_start()
    since = utcnow() - timedelta(days=30)
    signups = db.execute(select(func.date(User.created_at), func.count()).where(User.created_at >= since)
                         .group_by(func.date(User.created_at))).all()
    scans = db.execute(select(func.date(Analysis.created_at), func.count()).where(
        Analysis.created_at >= since, Analysis.parent_id.is_(None)).group_by(func.date(Analysis.created_at))).all()
    by_plan = dict(db.execute(select(Organization.plan_id, func.count()).group_by(Organization.plan_id)).all())
    mrr = db.scalar(select(func.coalesce(func.sum(Plan.price_monthly_cents), 0)).select_from(Organization)
                    .join(Plan, Plan.id == Organization.plan_id).where(Organization.status == "active"))
    return {
        "users": db.scalar(select(func.count(User.id))),
        "suspended_users": db.scalar(select(func.count(User.id)).where(User.status == "suspended")),
        "unverified_users": db.scalar(select(func.count(User.id)).where(User.email_verified_at.is_(None))),
        "workspaces": db.scalar(select(func.count(Organization.id))),
        "team_workspaces": db.scalar(select(func.count(Organization.id)).where(Organization.kind == "team")),
        "scans_this_month": db.scalar(select(func.count(Analysis.id)).where(
            Analysis.created_at >= start, Analysis.parent_id.is_(None))),
        "failed_this_month": db.scalar(select(func.count(Analysis.id)).where(
            Analysis.created_at >= start, Analysis.status == "failed")),
        "queued": db.scalar(select(func.count(Analysis.id)).where(Analysis.status.in_(("queued", "running")))),
        "by_plan": by_plan,
        "list_price_mrr_cents": mrr or 0,
        "signups_30d": [{"date": str(d), "count": c} for d, c in sorted(signups)],
        "scans_30d": [{"date": str(d), "count": c} for d, c in sorted(scans)],
        "settings": {"signups_open": setting(db, "signups_open"),
                     "require_email_verification": setting(db, "require_email_verification")},
        "email": email_status(),
    }


# ---------------------------------------------------------------- customers

def _user_out(db: Session, u: User) -> AdminUserOut:
    return AdminUserOut(
        id=u.id, email=u.email, role=u.role, status=u.status, email_verified=u.email_verified_at is not None,
        created_at=u.created_at, last_login_at=u.last_login_at,
        workspaces=db.scalar(select(func.count()).select_from(Membership).where(Membership.user_id == u.id)) or 0,
        scans_this_month=db.scalar(select(func.count(Analysis.id)).where(
            Analysis.user_id == u.id, Analysis.created_at >= month_start(), Analysis.parent_id.is_(None))) or 0)


@router.get("/users")
def list_users(_: User = Depends(require_platform_owner), db: Session = Depends(get_db),
               q: str | None = Query(None, max_length=200), status: str | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    stmt = select(User)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(User.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_user_out(db, u) for u in rows], "total": total, "page": page, "page_size": page_size}


def _target(db: Session, owner: User, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return u


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def patch_user(user_id: int, body: AdminUserPatch, request: Request, owner: User = Depends(require_platform_owner),
               db: Session = Depends(get_db)):
    u = _target(db, owner, user_id)
    if body.status is not None:
        if u.id == owner.id:
            raise HTTPException(400, "You can't suspend your own account")
        u.status = body.status
        if body.status == "suspended":
            accounts.revoke_sessions(db, u)
    if body.email_verified is not None:
        u.email_verified_at = utcnow() if body.email_verified else None
    audit(db, "admin.user_update", user_id=owner.id, target=str(u.id), request=request,
          detail=body.model_dump(exclude_none=True))
    return _user_out(db, u)


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def admin_revoke(user_id: int, request: Request, owner: User = Depends(require_platform_owner),
                 db: Session = Depends(get_db)):
    u = _target(db, owner, user_id)
    accounts.revoke_sessions(db, u)
    audit(db, "admin.revoke_sessions", user_id=owner.id, target=str(u.id), request=request)


@router.post("/users/{user_id}/send-reset", status_code=204)
def admin_send_reset(user_id: int, request: Request, owner: User = Depends(require_platform_owner),
                     db: Session = Depends(get_db)):
    u = _target(db, owner, user_id)
    sent = accounts.send_password_reset(db, u)
    if not sent.ok:
        raise HTTPException(502, f"The reset email could not be sent. {sent.error or ''}".strip())
    audit(db, "admin.send_reset", user_id=owner.id, target=str(u.id), request=request)


@router.post("/users/{user_id}/make-owner", response_model=AdminUserOut)
def make_owner(user_id: int, request: Request, owner: User = Depends(require_platform_owner),
               db: Session = Depends(get_db)):
    u = _target(db, owner, user_id)
    u.role = "owner"
    audit(db, "admin.grant_owner", user_id=owner.id, target=str(u.id), request=request)
    return _user_out(db, u)


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(user_id: int, request: Request, owner: User = Depends(require_platform_owner),
                      db: Session = Depends(get_db)):
    u = _target(db, owner, user_id)
    if u.id == owner.id:
        raise HTTPException(400, "Delete your own account from Settings instead")
    email = u.email
    accounts.delete_user(db, u)
    audit(db, "admin.user_delete", user_id=owner.id, target=str(user_id), request=request, detail={"email": email})


# ---------------------------------------------------------------- workspaces

def _org_out(db: Session, o: Organization) -> AdminOrgOut:
    owner_m = next((m for m in sorted(o.members, key=lambda m: m.created_at) if m.role == "owner"), None)
    return AdminOrgOut(id=o.id, name=o.name, kind=o.kind, status=o.status, plan_id=o.plan_id, plan_name=o.plan.name,
                       credits=o.credits, scan_quota_override=o.scan_quota_override, members=len(o.members),
                       owner_email=owner_m.user.email if owner_m else None, usage=usage(db, o).to_dict(),
                       created_at=o.created_at)


@router.get("/orgs")
def list_orgs(_: User = Depends(require_platform_owner), db: Session = Depends(get_db),
              q: str | None = Query(None, max_length=200), plan_id: str | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    stmt = select(Organization)
    if q:
        sub = select(Membership.org_id).join(User).where(User.email.ilike(f"%{q}%"))
        stmt = stmt.where(or_(Organization.name.ilike(f"%{q}%"), Organization.id.in_(sub)))
    if plan_id:
        stmt = stmt.where(Organization.plan_id == plan_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Organization.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_org_out(db, o) for o in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/orgs/{org_id}", response_model=AdminOrgOut)
def patch_org(org_id: int, body: AdminOrgPatch, request: Request, owner: User = Depends(require_platform_owner),
              db: Session = Depends(get_db)):
    o = db.get(Organization, org_id)
    if not o:
        raise HTTPException(404, "Workspace not found")
    if body.name is not None:
        o.name = body.name
    if body.plan_id is not None:
        if not db.get(Plan, body.plan_id):
            raise HTTPException(400, "Unknown plan")
        o.plan_id = body.plan_id
    if body.status is not None:
        o.status = body.status
    if body.credits_delta:
        o.credits = max(0, o.credits + body.credits_delta)
    if body.clear_quota_override:
        o.scan_quota_override = None
    elif body.scan_quota_override is not None:
        o.scan_quota_override = body.scan_quota_override
    db.commit()
    db.refresh(o)
    audit(db, "admin.org_update", user_id=owner.id, target=str(o.id), request=request,
          detail=body.model_dump(exclude_none=True, exclude_defaults=True))
    return _org_out(db, o)


# ---------------------------------------------------------------- plans

@router.get("/plans", response_model=list[PlanOut])
def list_plans(_: User = Depends(require_platform_owner), db: Session = Depends(get_db)):
    return db.scalars(select(Plan).order_by(Plan.sort)).all()


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, request: Request, owner: User = Depends(require_platform_owner),
                db: Session = Depends(get_db)):
    if db.get(Plan, body.id):
        raise HTTPException(409, "A plan with that id exists")
    p = Plan(**body.model_dump())
    db.add(p)
    db.commit()
    audit(db, "admin.plan_create", user_id=owner.id, target=p.id, request=request)
    return p


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def patch_plan(plan_id: str, body: PlanPatch, request: Request, owner: User = Depends(require_platform_owner),
               db: Session = Depends(get_db)):
    p = db.get(Plan, plan_id)
    if not p:
        raise HTTPException(404, "Plan not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    audit(db, "admin.plan_update", user_id=owner.id, target=p.id, request=request,
          detail=body.model_dump(exclude_none=True))
    return p


# ---------------------------------------------------------------- settings & audit

@router.get("/settings", response_model=PlatformSettingsIO)
def get_platform_settings(_: User = Depends(require_platform_owner), db: Session = Depends(get_db)):
    return PlatformSettingsIO(signups_open=setting(db, "signups_open"),
                              require_email_verification=setting(db, "require_email_verification"))


@router.patch("/settings", response_model=PlatformSettingsIO)
def patch_platform_settings(body: PlatformSettingsIO, request: Request, owner: User = Depends(require_platform_owner),
                            db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        row = db.get(PlatformSetting, k) or PlatformSetting(key=k)
        row.value = v
        db.add(row)
    db.commit()
    audit(db, "admin.settings", user_id=owner.id, request=request, detail=body.model_dump(exclude_none=True))
    return get_platform_settings(owner, db)


def email_status() -> dict:
    from ..config import get_settings
    s = get_settings()
    return {"delivery": mailer.delivery_mode(), "host": s.smtp_host, "port": s.smtp_port, "from": s.smtp_from,
            "app_url": s.app_url, "outbox_dir": str(s.outbox_dir.resolve()) if mailer.delivery_mode() == "outbox" else None}


@router.get("/email")
def get_email_status(_: User = Depends(require_platform_owner)):
    return email_status()


@router.post("/email/test")
def send_test_email(request: Request, owner: User = Depends(require_platform_owner), db: Session = Depends(get_db)):
    limiter_key = f"test-mail:{owner.id}"
    from ..ratelimit import limiter
    limiter.check(limiter_key, 5, 600)
    res = mailer.send(owner.email, "Test email", "This is a test email from your DeepShield AI server. "
                                                 "If you received it, email delivery is working.")
    audit(db, "admin.email_test", user_id=owner.id, request=request, detail={"ok": res.ok, "mode": res.mode})
    return {"ok": res.ok, "mode": res.mode, "error": res.error, "to": owner.email, **email_status()}


@router.get("/audit", response_model=list[AuditOut])
def audit_log(_: User = Depends(require_platform_owner), db: Session = Depends(get_db),
              limit: int = Query(100, ge=1, le=1000), action: str | None = None, user_id: int | None = None):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit)).all()
