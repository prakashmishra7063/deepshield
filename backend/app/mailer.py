"""Outgoing email.

With DS_SMTP_HOST and DS_SMTP_FROM set, mail is delivered over SMTP: implicit TLS on port 465,
otherwise STARTTLS (port 587; DS_SMTP_STARTTLS=false only for a trusted local relay). Without
them, in development, messages are written to DS_OUTBOX_DIR and logged, so links can still be
followed. In production an unconfigured mailer refuses to pretend it sent anything.
"""
import logging
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

from .config import get_settings

log = logging.getLogger("deepshield.mail")


@dataclass
class SendResult:
    ok: bool
    mode: str  # smtp | outbox | disabled
    error: str | None = None


def smtp_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from)


def delivery_mode() -> str:
    if smtp_configured():
        return "smtp"
    return "disabled" if get_settings().env == "production" else "outbox"


def send(to: str, subject: str, body: str) -> SendResult:
    s = get_settings()
    subject = f"[{s.product_name}] {subject}"
    mode = delivery_mode()
    if mode == "disabled":
        log.error("SMTP is not configured; email to a user was not sent")
        return SendResult(False, mode, "Email delivery is not configured on this server.")
    if mode == "outbox":
        s.outbox_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:40]
        path = s.outbox_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**9:09d}-{slug}.txt"
        path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n", encoding="utf-8")
        log.warning("SMTP not configured: email to %s was NOT sent, it was saved to %s", to, path.resolve())
        return SendResult(True, mode)

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg["Message-ID"] = make_msgid(domain=s.smtp_from.rsplit("@", 1)[-1].strip(">"))
    msg.set_content(body)
    ctx = ssl.create_default_context()
    try:
        if s.smtp_port == 465:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=ctx)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        with server as smtp:
            if s.smtp_port != 465 and s.smtp_starttls:
                smtp.starttls(context=ctx)
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        log.info("email sent to %s via %s", to, s.smtp_host)
        return SendResult(True, mode)
    except smtplib.SMTPAuthenticationError:
        log.exception("SMTP authentication failed")
        return SendResult(False, mode, "The email server rejected the username or password (for Gmail, use an "
                                       "App Password, not your normal password).")
    except (smtplib.SMTPException, OSError) as e:
        log.exception("Failed to send email")
        return SendResult(False, mode, f"Could not send email: {type(e).__name__}: {str(e)[:200]}")


def link(path: str) -> str:
    return get_settings().app_url.rstrip("/") + path
