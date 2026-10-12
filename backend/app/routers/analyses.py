import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import storage
from ..audit import audit
from ..config import get_settings
from ..db import get_db
from ..billing import charge_scan, check_can_scan, upload_limit_mb
from ..deps import Ctx, get_ctx, require_verified
from ..detection.sniff import sniff
from ..models import Alert, Analysis, Case, Membership
from ..netguard import FetchError, validate_url
from ..pipeline import store_media
from ..ratelimit import limiter
from ..reports import report_json, report_pdf
from ..schemas import AnalysisOut, AnalysisSummary, Page, ReportLinkIn, ReportLinkOut, UrlScanIn
from ..security import sign_report_link, verify_report_link
from ..worker import jobs

router = APIRouter(tags=["analyses"])


def summary(a: Analysis) -> AnalysisSummary:
    s = AnalysisSummary.model_validate(a)
    s.file_name = a.media.original_name if a.media else None
    return s


def detail(a: Analysis) -> AnalysisOut:
    out = AnalysisOut(**summary(a).model_dump(), result=a.result_json)
    out.media_available = bool(a.media and a.media.storage_path)
    return out


def owned(db: Session, ctx: Ctx, analysis_id: str) -> Analysis:
    """An analysis in the caller's active workspace (404 otherwise, so IDs can't be probed)."""
    a = db.get(Analysis, analysis_id)
    if not a or a.org_id != ctx.org.id:
        raise HTTPException(404, "Analysis not found")
    return a


def _scan_rate(ctx: Ctx) -> None:
    limiter.check(f"scan:{ctx.user.id}", get_settings().scan_rate_limit_per_hour, 3600)


@router.post("/analyses/upload", response_model=AnalysisOut, status_code=202)
async def upload(request: Request, file: UploadFile = File(...), ctx: Ctx = Depends(require_verified),
                 db: Session = Depends(get_db)):
    _scan_rate(ctx)
    quota = check_can_scan(db, ctx.org)
    limit_mb = upload_limit_mb(ctx.org)
    limit = limit_mb * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(413, f"File exceeds the {limit_mb} MB upload limit of the {ctx.org.plan.name} plan")
    if not buf:
        raise HTTPException(400, "Empty file")
    sn = sniff(bytes(buf[:64]))
    if not sn:
        raise HTTPException(415, "Unsupported or unrecognized file type. Supported: images (JPG, PNG, WEBP, GIF, BMP, "
                                 "TIFF), video (MP4, MOV, WEBM, AVI) and audio (WAV, MP3, M4A, OGG, FLAC).")
    if not sn.supported:
        raise HTTPException(415, f"{sn.mime} is not supported yet. {sn.note or ''}".strip())
    media = store_media(db, bytes(buf), kind=sn.kind, mime=sn.mime, name=(file.filename or "upload")[-255:])
    a = Analysis(org_id=ctx.org.id, user_id=ctx.user.id, source_type="upload", media_id=media.id, kind=sn.kind)
    db.add(a)
    charge_scan(db, ctx.org, quota)
    db.commit()
    audit(db, "analysis.create", user_id=ctx.user.id, target=a.id, request=request,
          detail={"source": "upload", "kind": sn.kind, "size": len(buf)})
    jobs.enqueue(a.id)
    return detail(a)


@router.post("/analyses/url", response_model=AnalysisOut, status_code=202)
def scan_url(body: UrlScanIn, request: Request, ctx: Ctx = Depends(require_verified), db: Session = Depends(get_db)):
    _scan_rate(ctx)
    quota = check_can_scan(db, ctx.org)
    try:
        url = validate_url(body.url)
    except FetchError as e:
        raise HTTPException(400, str(e))
    page_url = body.page_url if body.page_url and body.page_url.startswith(("http://", "https://")) else None
    source = "extension" if getattr(request.state, "via_api_token", False) or body.source == "extension" else "url"
    a = Analysis(org_id=ctx.org.id, user_id=ctx.user.id, source_type=source, source_url=url, page_url=page_url)
    db.add(a)
    charge_scan(db, ctx.org, quota)
    db.commit()
    audit(db, "analysis.create", user_id=ctx.user.id, target=a.id, request=request, detail={"source": source})
    jobs.enqueue(a.id)
    return detail(a)


@router.get("/analyses", response_model=Page)
def history(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
            page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
            classification: str | None = None, kind: str | None = None, status: str | None = None,
            q: str | None = Query(None, max_length=200)):
    stmt = select(Analysis).where(Analysis.org_id == ctx.org.id)
    if classification:
        stmt = stmt.where(Analysis.classification == classification)
    if kind:
        stmt = stmt.where(Analysis.kind == kind)
    if status:
        stmt = stmt.where(Analysis.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Analysis.id.ilike(like) | Analysis.source_url.ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Analysis.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[summary(a) for a in rows], total=total, page=page, page_size=page_size)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return detail(owned(db, ctx, analysis_id))


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, request: Request, ctx: Ctx = Depends(get_ctx),
                    db: Session = Depends(get_db)):
    a = owned(db, ctx, analysis_id)
    if ctx.role == "member" and a.user_id != ctx.user.id:
        raise HTTPException(403, "Only workspace admins can delete analyses created by others")
    if a.status in ("queued", "running"):
        raise HTTPException(409, "Wait for the analysis to finish before deleting it")
    media = a.media
    db.delete(a)
    db.flush()
    if media and not db.scalar(select(func.count(Analysis.id)).where(Analysis.media_id == media.id)):
        storage.delete_original(media.storage_path)
        db.delete(media)
    db.commit()
    storage.delete_derived(analysis_id)
    audit(db, "analysis.delete", user_id=ctx.user.id, target=analysis_id, request=request)


@router.get("/analyses/{analysis_id}/evidence/{name}")
def evidence(analysis_id: str, name: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    owned(db, ctx, analysis_id)
    path = storage.derived_file(analysis_id, name)
    if not path or path.suffix.lower() not in (".png", ".jpg"):
        raise HTTPException(404, "Evidence not found")
    return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg",
                        headers={"Cache-Control": "private, max-age=300"})


@router.post("/analyses/{analysis_id}/report-link", response_model=ReportLinkOut)
def report_link(analysis_id: str, body: ReportLinkIn, request: Request, ctx: Ctx = Depends(get_ctx),
                db: Session = Depends(get_db)):
    a = owned(db, ctx, analysis_id)
    if a.status not in ("completed", "failed"):
        raise HTTPException(409, "The report is available once the analysis has finished")
    token = sign_report_link(a.id, ctx.user.id, body.format)
    audit(db, "report.link", user_id=ctx.user.id, target=a.id, request=request, detail={"format": body.format})
    return ReportLinkOut(url=f"/api/v1/reports/{token}", expires_in=get_settings().report_link_minutes * 60)


@router.get("/reports/{token}", include_in_schema=True)
def download_report(token: str, db: Session = Depends(get_db)):
    data = verify_report_link(token)
    if not data:
        raise HTTPException(403, "This report link is invalid or has expired")
    a = db.get(Analysis, data["a"])
    # The signer must still belong to the analysis's workspace.
    if not a or not db.get(Membership, (a.org_id, data["u"])):
        raise HTTPException(404, "Report not found")
    headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}
    if data["f"] == "json":
        headers["Content-Disposition"] = f'attachment; filename="deepshield-{a.id}.json"'
        return Response(json.dumps(report_json(a), indent=2), media_type="application/json", headers=headers)
    headers["Content-Disposition"] = f'attachment; filename="deepshield-{a.id}.pdf"'
    return Response(report_pdf(a), media_type="application/pdf", headers=headers)


@router.get("/dashboard/summary")
def dashboard(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    base = select(Analysis).where(Analysis.org_id == ctx.org.id)
    rows = db.execute(select(Analysis.classification, Analysis.kind, Analysis.status, Analysis.created_at)
                      .where(Analysis.org_id == ctx.org.id)).all()
    by_class: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    trend: dict[str, dict[str, int]] = {}
    for cls, kind, status, created in rows:
        if status == "completed":
            by_class[cls] = by_class.get(cls, 0) + 1
            by_kind[kind or "unknown"] = by_kind.get(kind or "unknown", 0) + 1
            day = created.date().isoformat()
            d = trend.setdefault(day, {"total": 0, "flagged": 0})
            d["total"] += 1
            if cls in ("potentially_manipulated", "high_risk"):
                d["flagged"] += 1
    recent = db.scalars(base.order_by(Analysis.created_at.desc()).limit(8)).all()
    open_cases = db.scalar(select(func.count(Case.id)).where(Case.org_id == ctx.org.id, Case.status == "open"))
    new_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.user_id == ctx.user.id, Alert.state == "new"))
    return {
        "total": len(rows),
        "completed": sum(by_class.values()),
        "in_progress": sum(1 for r in rows if r[2] in ("queued", "running")),
        "failed": sum(1 for r in rows if r[2] == "failed"),
        "potentially_manipulated": by_class.get("potentially_manipulated", 0),
        "high_risk": by_class.get("high_risk", 0),
        "by_classification": by_class,
        "by_kind": by_kind,
        "trend": [{"date": k, **v} for k, v in sorted(trend.items())[-30:]],
        "recent": [summary(a).model_dump(mode="json") for a in recent],
        "open_cases": open_cases,
        "new_alerts": new_alerts,
    }
