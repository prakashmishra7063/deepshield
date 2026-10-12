"""Plans, monthly quotas and pay-per-scan credits.

A workspace may run `plan.monthly_scans` (or its override) top-level scans per
calendar month (UTC). Beyond that each scan consumes one credit. Media found on
scanned pages (child analyses) is never billed. Payment collection (Stripe) is
a separate step; credits and plans can be granted from the owner console.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Analysis, Organization, Plan, PlatformSetting

DEFAULT_PLANS = [
    {"id": "free", "name": "Free", "description": "Try DeepShield on a few files a month.",
     "monthly_scans": 10, "max_upload_mb": 10, "max_members": 1, "price_monthly_cents": 0, "sort": 0},
    {"id": "pro", "name": "Pro", "description": "For journalists, creators and investigators.",
     "monthly_scans": 300, "max_upload_mb": 100, "max_members": 1, "price_monthly_cents": 1900, "sort": 1},
    {"id": "business", "name": "Business", "description": "Team workspace with shared investigations.",
     "monthly_scans": 2000, "max_upload_mb": 100, "max_members": 10, "price_monthly_cents": 9900, "sort": 2},
    {"id": "internal", "name": "Internal (unlimited)", "description": "Platform owner and staff.",
     "monthly_scans": -1, "max_upload_mb": 100, "max_members": 50, "price_monthly_cents": 0, "public": False,
     "sort": 9},
]

DEFAULT_SETTINGS = {"signups_open": True, "require_email_verification": True}


def seed(db: Session) -> None:
    for p in DEFAULT_PLANS:
        if not db.get(Plan, p["id"]):
            db.add(Plan(**p))
    for k, v in DEFAULT_SETTINGS.items():
        if not db.get(PlatformSetting, k):
            db.add(PlatformSetting(key=k, value=v))
    db.commit()


def setting(db: Session, key: str):
    row = db.get(PlatformSetting, key)
    return row.value if row else DEFAULT_SETTINGS.get(key)


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@dataclass
class Usage:
    used: int
    limit: int  # -1 = unlimited
    credits: int
    period_start: datetime

    @property
    def remaining_in_plan(self) -> int | None:
        return None if self.limit < 0 else max(0, self.limit - self.used)

    def to_dict(self) -> dict:
        return {"used": self.used, "limit": self.limit, "credits": self.credits,
                "remaining_in_plan": self.remaining_in_plan,
                "period_start": self.period_start.isoformat().replace("+00:00", "Z")}


def usage(db: Session, org: Organization) -> Usage:
    start = month_start()
    used = db.scalar(select(func.count(Analysis.id)).where(
        Analysis.org_id == org.id, Analysis.parent_id.is_(None), Analysis.created_at >= start))
    limit = org.scan_quota_override if org.scan_quota_override is not None else org.plan.monthly_scans
    return Usage(used or 0, limit, org.credits, start)


def upload_limit_mb(org: Organization) -> int:
    return min(org.plan.max_upload_mb, get_settings().max_upload_mb)


def check_can_scan(db: Session, org: Organization) -> Usage:
    if org.status != "active":
        raise HTTPException(403, "This workspace is suspended. Contact support.")
    u = usage(db, org)
    if u.limit >= 0 and u.used >= u.limit and org.credits <= 0:
        raise HTTPException(402, f"You've used all {u.limit} scans included in the {org.plan.name} plan this month. "
                                 "Upgrade your plan or add scan credits to continue.")
    return u


def charge_scan(db: Session, org: Organization, u: Usage) -> None:
    """Call after a billable scan was created; uses a credit once the plan quota is exhausted."""
    if u.limit >= 0 and u.used >= u.limit:
        org.credits = max(0, org.credits - 1)
