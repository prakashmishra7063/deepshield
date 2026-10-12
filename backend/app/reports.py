"""Evidence report generation (JSON and PDF)."""
import io
from datetime import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from . import storage
from .detection.ensemble import LABELS
from .models import Analysis

DISCLAIMER = ("This report gives automated, probabilistic indicators. It is not proof that content is authentic or "
              "manipulated, and it makes no claim about the intent, identity or conduct of any person depicted. "
              "Get qualified forensic review before relying on it for legal, financial or reputational decisions.")

CLASS_COLORS = {"likely_authentic": "#15803d", "uncertain": "#64748b", "potentially_manipulated": "#b45309",
                "high_risk": "#b91c1c"}


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def report_json(a: Analysis) -> dict:
    r = a.result_json or {}
    return {
        "report_type": "DeepShield AI Evidence Report",
        "analysis_id": a.id,
        "created_at": _iso(a.created_at),
        "completed_at": _iso(a.completed_at),
        "status": a.status,
        "source": {"type": a.source_type, "url": a.source_url, "page_url": a.page_url},
        "media": r.get("media"),
        "assessment": r.get("assessment"),
        "detection_methods": r.get("detectors"),
        "indicators": r.get("signals"),
        "evidence_files": [e.get("name") for e in r.get("evidence", [])],
        "limitations": r.get("limitations"),
        "recommended_next_steps": r.get("next_steps"),
        "pipeline_version": r.get("pipeline_version"),
        "disclaimer": DISCLAIMER,
        "error": a.error,
    }


def report_pdf(a: Analysis) -> bytes:
    r = a.result_json or {}
    asmt = r.get("assessment") or {}
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#475569"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
    P = lambda t, st=body: Paragraph(escape(str(t)) if t is not None else "—", st)  # noqa: E731

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"DeepShield report {a.id}", author="DeepShield AI")
    el = [Paragraph("<b>DeepShield AI</b> — Evidence Report", ss["Title"]),
          P("See Beyond the Fake. Protect What's Real.", small), Spacer(1, 6)]

    cls = asmt.get("classification") or "uncertain"
    color = colors.HexColor(CLASS_COLORS.get(cls, "#64748b"))
    badge = Table([[Paragraph(f"<font color='white'><b>{escape(LABELS.get(cls, cls))}</b></font>", body)]],
                  colWidths=[174 * mm])
    badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el += [badge, Spacer(1, 4), P(asmt.get("summary") or a.error or "")]

    media = r.get("media") or {}
    like = asmt.get("likelihood")
    rows = [
        ["Analysis ID", a.id], ["Analyzed", _iso(a.completed_at or a.created_at)],
        ["Content type", f"{media.get('kind', a.kind)} ({media.get('mime', '—')})"],
        ["Source", a.source_url or media.get("name") or "Uploaded file"],
        ["SHA-256 (original)", media.get("sha256", "—")],
        ["Synthetic origin", (asmt.get("synthetic_origin") or "unknown").replace("_", " ")],
        ["Reliability", asmt.get("reliability", "—")],
        ["Calibrated likelihood", f"{like:.0%}" if like is not None else "Not shown (no calibrated model ran)"],
        ["Categories", ", ".join(asmt.get("categories") or []) or "—"],
    ]
    if a.page_url:
        rows.insert(4, ["Found on page", a.page_url])
    t = Table([[P(k, small), P(v)] for k, v in rows], colWidths=[42 * mm, 132 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9"))]))
    el += [Spacer(1, 8), t]

    el.append(Paragraph("Indicators", h2))
    sigs = r.get("signals") or []
    if sigs:
        data = [[P("Indicator", small), P("Strength", small), P("Points to", small), P("Detail", small)]]
        for s in sigs:
            ts = f" (at {s['timestamp_s']}s)" if s.get("timestamp_s") is not None else ""
            data.append([P(s["title"] + ts), P(s["strength"]), P(s["direction"]), P(s["detail"], small)])
        st = Table(data, colWidths=[45 * mm, 18 * mm, 22 * mm, 89 * mm], repeatRows=1)
        st.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        el.append(st)
    else:
        el.append(P("No indicators were raised by the detectors that ran."))

    el.append(Paragraph("Detection methods", h2))
    dm = [[P("Detector", small), P("Status", small), P("Notes", small)]]
    for d in r.get("detectors") or []:
        note = d.get("reason") or ("calibrated" if d.get("calibrated") else "heuristic / uncalibrated")
        dm.append([P(f"{d['name']} v{d['version']}"), P(d["status"]), P(note, small)])
    dt = Table(dm, colWidths=[50 * mm, 22 * mm, 102 * mm], repeatRows=1)
    dt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
    el.append(dt)

    ev = [e for e in r.get("evidence") or [] if storage.derived_file(a.id, e["name"])]
    if ev:
        el.append(Paragraph("Visual evidence", h2))
        el.append(P("Annotated or derived images. The original file is stored separately and is not modified.", small))
        for e in ev[:8]:
            path = storage.derived_file(a.id, e["name"])
            try:
                img = RLImage(str(path))
                w, h = img.imageWidth, img.imageHeight
                scale = min(170 * mm / w, 80 * mm / h, 1.0 if w > 400 else 2.0)
                img.drawWidth, img.drawHeight = w * scale, h * scale
                el.append(KeepTogether([Spacer(1, 4), img, P(e.get("caption", ""), small)]))
            except Exception:
                continue

    for title, key in (("Limitations", "limitations"), ("Recommended next steps", "next_steps")):
        el.append(Paragraph(title, h2))
        for item in r.get(key) or []:
            el.append(P("• " + item))

    el += [Spacer(1, 10), P(DISCLAIMER, small)]
    doc.build(el)
    return buf.getvalue()
