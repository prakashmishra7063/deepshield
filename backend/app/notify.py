import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from .config import get_settings
from .detection.ensemble import LABELS, ORDER
from .models import Alert, Analysis, User

log = logging.getLogger("deepshield.notify")
ALERTABLE = {"potentially_manipulated", "high_risk"}


def maybe_alert(db: Session, analysis: Analysis, user: User) -> Alert | None:
    cls = analysis.classification
    if cls not in ALERTABLE:
        return None
    threshold = user.alert_threshold if user.alert_threshold in ORDER else "potentially_manipulated"
    if ORDER.index(cls) < ORDER.index(threshold):
        return None
    what = analysis.kind or "content"
    src = analysis.source_url or (analysis.media.original_name if analysis.media else None) or analysis.id
    alert = Alert(user_id=user.id, analysis_id=analysis.id, level=cls,
                  title=f"{LABELS[cls]}: {what} {src[:120]}")
    db.add(alert)
    db.commit()
    if user.email_alerts:
        send_email(user.email, alert.title,
                   f"DeepShield flagged analysis {analysis.id} as '{LABELS[cls]}'.\n\n"
                   f"{(analysis.result_json or {}).get('assessment', {}).get('summary', '')}\n\n"
                   "Open DeepShield to review the evidence. This is an automated estimate, not proof.")
    return alert


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not (s.smtp_host and s.smtp_from):
        log.info("Email alerts not configured; skipped message to user")
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, f"[DeepShield] {subject}"
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception("Failed to send alert email")
        return False
