"""Analysis orchestration: fetch (for URLs) → sniff → detectors → ensemble → persist → alert."""
import logging
import time
import traceback
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from . import storage
from .db import SessionLocal
from .detection.base import DetectorReport, MediaContext
from .detection.ensemble import assess
from .detection.registry import detectors_for
from .detection.sniff import looks_like_html, sniff
from .detection.web import discover_media, parse_page
from .integrations import platform_for_host
from .models import Analysis, MediaObject, User, utcnow
from .netguard import FetchError, safe_fetch
from .notify import maybe_alert

log = logging.getLogger("deepshield.pipeline")
PIPELINE_VERSION = "1.0.0"
MAX_EMBEDDED = 2


class UserFacingError(Exception):
    pass


def _progress(db: Session, a: Analysis):
    last = [0.0]

    def update(pct: int, stage: str) -> None:
        now = time.monotonic()
        if now - last[0] < 0.3 and pct < 100:
            return
        last[0] = now
        a.progress, a.stage = max(a.progress, min(pct, 99)), stage[:100]
        db.commit()
    return update


def store_media(db: Session, data: bytes, *, kind: str, mime: str, name: str | None = None,
                source_url: str | None = None) -> MediaObject:
    rel, sha = storage.save_original(data)
    m = MediaObject(sha256=sha, mime=mime, kind=kind, size=len(data), original_name=(name or "")[:255] or None,
                    storage_path=rel, source_url=source_url)
    db.add(m)
    db.flush()
    return m


def _fetch_into(db: Session, a: Analysis, progress) -> None:
    progress(5, "Fetching URL safely")
    try:
        res = safe_fetch(a.source_url)
    except FetchError as e:
        raise UserFacingError(str(e)) from e
    if res.truncated:
        raise UserFacingError("Remote content exceeds the maximum download size")
    sn = sniff(res.data[:64])
    if sn:
        if not sn.supported:
            raise UserFacingError(f"Unsupported media format ({sn.mime}). {sn.note or ''}".strip())
        a.media = store_media(db, res.data, kind=sn.kind, mime=sn.mime, source_url=res.url)
        a.kind = sn.kind
    elif res.content_type in ("text/html", "application/xhtml+xml") or looks_like_html(res.data):
        a.media = store_media(db, res.data, kind="html", mime="text/html", source_url=res.url)
        a.kind = "html"
    else:
        raise UserFacingError(f"The URL returned content that cannot be analyzed ({res.content_type or 'unknown type'})")
    a.source_url = res.url
    db.commit()


def run_detectors(ctx: MediaContext) -> list[DetectorReport]:
    dets = detectors_for(ctx.kind)
    reports = []
    for i, d in enumerate(dets):
        ctx.progress(20 + int(70 * i / max(len(dets), 1)), f"Running {d.name.replace('_', ' ')}")
        ok, reason = d.availability()
        if not ok:
            reports.append(d.report("unavailable", reason=reason))
            continue
        try:
            reports.append(d.run(ctx))
        except Exception as e:  # a failing detector must never take down the analysis
            log.warning("detector %s failed: %s", d.name, traceback.format_exc(limit=3))
            reports.append(d.report("error", reason=f"Detector error: {type(e).__name__}"))
    return reports


def process(analysis_id: str, enqueue=None) -> None:
    db = SessionLocal()
    try:
        a = db.get(Analysis, analysis_id)
        if not a or a.status not in ("queued", "running"):
            return
        a.status, a.started_at, a.stage, a.progress = "running", utcnow(), "Starting", 1
        db.commit()
        progress = _progress(db, a)
        try:
            if a.media is None:
                if not a.source_url:
                    raise UserFacingError("Nothing to analyze")
                _fetch_into(db, a, progress)
            media = a.media
            if media is None or not media.storage_path:
                raise UserFacingError("The original media is no longer available")
            data = storage.read_original(media.storage_path)
            ctx = MediaContext(analysis_id=a.id, data=data, kind=media.kind, mime=media.mime,
                               path=storage.original_path(media.storage_path), out_dir=storage.derived_dir(a.id),
                               source_url=a.source_url, progress=progress)
            extra: dict = {}
            embedded: list[dict] = []
            if media.kind == "html":
                page = parse_page(data, a.source_url or "")
                ctx.cache["page"] = page
                for kind, url in discover_media(page)[:MAX_EMBEDDED]:
                    child = Analysis(user_id=a.user_id, source_type="url", source_url=url,
                                     page_url=a.source_url, kind=kind, stage="Queued (embedded media)")
                    db.add(child)
                    db.flush()
                    embedded.append({"analysis_id": child.id, "url": url, "kind": kind})
                db.commit()
                if enqueue:
                    for e in embedded:
                        enqueue(e["analysis_id"])

            reports = run_detectors(ctx)
            progress(92, "Combining evidence")
            assessment = assess(media.kind, reports)

            host = urlparse(a.source_url or a.page_url or "").hostname or ""
            platform = platform_for_host(host) if host else None
            if platform:
                extra["platform"] = {"id": platform["id"], "name": platform["name"], "status": platform["status"],
                                     "detail": platform["detail"]}
                assessment["limitations"].append(f"{platform['name']}: {platform['detail']}")
            if media.kind == "html":
                extra["embedded_media"] = embedded
                if not embedded:
                    assessment["limitations"].append("No analyzable media was found on this page.")

            signals = [s.to_dict() for r in reports for s in r.signals]
            signals.sort(key=lambda s: ({"strong": 0, "moderate": 1, "weak": 2}[s["strength"]],
                                        {"manipulated": 0, "synthetic": 1, "authentic": 2, "neutral": 3}[s["direction"]]))
            evidence = [vars(e) for r in reports for e in r.evidence]
            facts = {r.name: r.facts for r in reports if r.facts}
            a.result_json = {
                "pipeline_version": PIPELINE_VERSION,
                "assessment": {k: assessment[k] for k in ("classification", "label", "summary", "likelihood",
                                                          "likelihood_calibrated", "reliability", "synthetic_origin",
                                                          "categories")},
                "signals": signals,
                "detectors": [r.summary() for r in reports],
                "evidence": evidence,
                "facts": facts,
                "limitations": assessment["limitations"],
                "next_steps": assessment["next_steps"],
                "media": {"kind": media.kind, "mime": media.mime, "sha256": media.sha256, "size": media.size,
                          "name": media.original_name, "source_url": media.source_url},
                **extra,
            }
            a.classification = assessment["classification"]
            a.synthetic_origin = assessment["synthetic_origin"]
            a.likelihood = assessment["likelihood"]
            a.kind = media.kind
            a.status, a.progress, a.stage, a.completed_at = "completed", 100, "Completed", utcnow()
            db.commit()
            user = db.get(User, a.user_id)
            if user:
                maybe_alert(db, a, user)
        except UserFacingError as e:
            db.rollback()
            a.status, a.error, a.stage, a.completed_at = "failed", str(e), "Failed", utcnow()
            db.commit()
        except Exception:
            log.exception("analysis %s crashed", analysis_id)
            db.rollback()
            a.status, a.error, a.stage, a.completed_at = "failed", "Internal error while analyzing this content", "Failed", utcnow()
            db.commit()
    finally:
        db.close()
