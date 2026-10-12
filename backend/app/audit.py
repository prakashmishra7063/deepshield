from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog
from .ratelimit import client_ip


def audit(db: Session, action: str, *, user_id: int | None = None, target: str | None = None,
          request: Request | None = None, detail: dict | None = None, commit: bool = True) -> None:
    db.add(AuditLog(user_id=user_id, action=action, target=target,
                    ip=client_ip(request) if request else None, detail=detail))
    if commit:
        db.commit()
