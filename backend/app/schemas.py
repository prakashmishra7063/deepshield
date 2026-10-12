from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer


def _utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_utc, return_type=str)]

Classification = Literal["likely_authentic", "uncertain", "potentially_manipulated", "high_risk"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    accept_terms: bool = Field(description="Must accept the responsible-use terms")
    invite_token: str | None = Field(default=None, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORM):
    id: int
    email: str
    role: str
    alert_threshold: str
    email_alerts: bool
    created_at: UTCDateTime


class SettingsIn(BaseModel):
    alert_threshold: Literal["potentially_manipulated", "high_risk"] | None = None
    email_alerts: bool | None = None


class ApiTokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiTokenOut(ORM):
    id: int
    name: str
    prefix: str
    revoked: bool
    last_used_at: UTCDateTime | None
    created_at: UTCDateTime


class ApiTokenCreated(ApiTokenOut):
    token: str


class UrlScanIn(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    page_url: str | None = Field(default=None, max_length=4096)
    source: Literal["url", "extension"] = "url"


class AnalysisSummary(ORM):
    id: str
    source_type: str
    source_url: str | None
    page_url: str | None
    kind: str | None
    status: str
    progress: int
    stage: str
    classification: str | None
    synthetic_origin: str | None
    likelihood: float | None
    error: str | None
    created_at: UTCDateTime
    completed_at: UTCDateTime | None
    file_name: str | None = None


class AnalysisOut(AnalysisSummary):
    result: dict | None = None
    media_available: bool = False


class Page(BaseModel):
    items: list[AnalysisSummary]
    total: int
    page: int
    page_size: int


class ReportLinkIn(BaseModel):
    format: Literal["pdf", "json"] = "pdf"


class ReportLinkOut(BaseModel):
    url: str
    expires_in: int


class CaseIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    analysis_id: str | None = None


class CasePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["open", "reported", "resolved", "dismissed"] | None = None


class CaseItemIn(BaseModel):
    analysis_id: str


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class NoteOut(ORM):
    id: int
    body: str
    user_id: int
    created_at: UTCDateTime


class CaseOut(ORM):
    id: int
    title: str
    status: str
    created_at: UTCDateTime
    updated_at: UTCDateTime
    item_count: int = 0


class CaseDetail(CaseOut):
    items: list[AnalysisSummary]
    notes: list[NoteOut]


class AlertOut(ORM):
    id: int
    analysis_id: str | None
    level: str
    title: str
    state: str
    created_at: UTCDateTime


class AlertPatch(BaseModel):
    state: Literal["acknowledged", "dismissed", "new"]


class AuditOut(ORM):
    id: int
    user_id: int | None
    action: str
    target: str | None
    ip: str | None
    detail: dict | None
    created_at: UTCDateTime


# ---------------------------------------------------------------- accounts & workspaces

class MembershipOut(BaseModel):
    org_id: int
    name: str
    kind: str
    role: str
    plan_id: str


class MeOut(BaseModel):
    id: int
    email: str
    role: str
    status: str
    email_verified: bool
    alert_threshold: str
    email_alerts: bool
    created_at: UTCDateTime
    active_org_id: int | None
    memberships: list[MembershipOut]
    require_email_verification: bool
    # How this server delivers email: smtp (real inbox) | outbox (dev: saved to files) | disabled
    email_delivery: str


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=10, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=256)
    confirm: Literal["DELETE"]


class SwitchOrgIn(BaseModel):
    org_id: int


class PlanOut(ORM):
    id: str
    name: str
    description: str
    monthly_scans: int
    max_upload_mb: int
    max_members: int
    price_monthly_cents: int
    currency: str
    public: bool
    sort: int


class PlanIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{2,40}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    monthly_scans: int = Field(ge=-1)
    max_upload_mb: int = Field(ge=1, le=2048)
    max_members: int = Field(ge=1, le=10000)
    price_monthly_cents: int = Field(ge=0)
    currency: str = Field(default="usd", min_length=3, max_length=3)
    public: bool = True
    sort: int = 0


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    monthly_scans: int | None = Field(default=None, ge=-1)
    max_upload_mb: int | None = Field(default=None, ge=1, le=2048)
    max_members: int | None = Field(default=None, ge=1, le=10000)
    price_monthly_cents: int | None = Field(default=None, ge=0)
    public: bool | None = None
    sort: int | None = None


class MemberOut(BaseModel):
    user_id: int
    email: str
    role: str
    joined_at: UTCDateTime


class InviteIn(BaseModel):
    email: EmailStr
    role: Literal["member", "admin"] = "member"


class InviteOut(ORM):
    id: int
    email: str
    role: str
    expires_at: UTCDateTime
    created_at: UTCDateTime


class InvitePreview(BaseModel):
    org_name: str
    email: str
    role: str
    inviter: str | None


class OrgOut(BaseModel):
    id: int
    name: str
    kind: str
    status: str
    my_role: str
    plan: PlanOut
    usage: dict
    seats_used: int
    members: list[MemberOut]
    invites: list[InviteOut]


class OrgCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class OrgPatch(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class MemberPatch(BaseModel):
    role: Literal["member", "admin", "owner"]


# ---------------------------------------------------------------- owner console

class AdminUserOut(BaseModel):
    id: int
    email: str
    role: str
    status: str
    email_verified: bool
    created_at: UTCDateTime
    last_login_at: UTCDateTime | None
    workspaces: int
    scans_this_month: int


class AdminUserPatch(BaseModel):
    status: Literal["active", "suspended"] | None = None
    email_verified: bool | None = None


class AdminOrgOut(BaseModel):
    id: int
    name: str
    kind: str
    status: str
    plan_id: str
    plan_name: str
    credits: int
    scan_quota_override: int | None
    members: int
    owner_email: str | None
    usage: dict
    created_at: UTCDateTime


class AdminOrgPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    plan_id: str | None = None
    status: Literal["active", "suspended"] | None = None
    credits_delta: int | None = Field(default=None, ge=-1_000_000, le=1_000_000)
    scan_quota_override: int | None = Field(default=None, ge=-1)
    clear_quota_override: bool = False


class PlatformSettingsIO(BaseModel):
    signups_open: bool | None = None
    require_email_verification: bool | None = None
