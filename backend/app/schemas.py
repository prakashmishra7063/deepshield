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
