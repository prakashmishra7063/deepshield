import shutil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..detection.registry import health
from ..integrations import integration_status
from ..models import Analysis, AuditLog, User
from ..pipeline import PIPELINE_VERSION
from ..schemas import AuditOut
from ..worker import jobs

router = APIRouter(tags=["system"])


@router.get("/system/health")
def system_health(db: Session = Depends(get_db)):
    db.execute(select(1))
    dets = health()
    return {
        "status": "ok",
        "pipeline_version": PIPELINE_VERSION,
        "queue_depth": jobs.q.qsize(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "detectors": dets,
        "models_configured": any(d["category"] == "model" and d["available"] for d in dets),
    }


@router.get("/integrations")
def integrations(_: User = Depends(get_current_user)):
    return integration_status()


@router.get("/admin/audit", response_model=list[AuditOut])
def audit_log(_: User = Depends(require_admin), db: Session = Depends(get_db),
              limit: int = Query(100, ge=1, le=1000), action: str | None = None):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit)).all()


@router.get("/admin/stats")
def admin_stats(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "users": db.scalar(select(func.count(User.id))),
        "analyses": db.scalar(select(func.count(Analysis.id))),
        "by_status": dict(db.execute(select(Analysis.status, func.count()).group_by(Analysis.status)).all()),
    }
