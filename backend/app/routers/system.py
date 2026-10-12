import shutil

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..detection.registry import health
from ..integrations import integration_status
from ..models import User
from ..pipeline import PIPELINE_VERSION
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
