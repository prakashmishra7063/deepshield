"""Integration registry. Each entry states plainly whether it is operational,
needs credentials, or is planned. The UI and docs render this list directly."""
import shutil

from .config import get_settings

# status: operational | limited | requires_credentials | planned
PLATFORMS = [
    {"id": "upload", "name": "Direct file upload", "category": "core", "status": "operational",
     "detail": "JPG, PNG, WEBP, GIF, BMP, TIFF, MP4, MOV, WEBM, AVI, WAV. MP3/M4A/OGG/FLAC need ffmpeg."},
    {"id": "public_url", "name": "Public URL scanning", "category": "core", "status": "operational",
     "detail": "Direct media links and public web pages (OpenGraph media + impersonation checks), fetched through the SSRF guard."},
    {"id": "browser_extension", "name": "Chrome / Edge extension", "category": "core", "status": "operational",
     "detail": "One-click scanning of images and videos on pages you visit, using a personal API token."},
    {"id": "youtube", "name": "YouTube", "category": "social", "status": "limited", "hosts": ["youtube.com", "youtu.be"],
     "detail": "Public page metadata and thumbnails only. Video streams can't be retrieved without an authorized "
               "integration. Upload the file you're allowed to analyze instead."},
    {"id": "x", "name": "X (Twitter)", "category": "social", "status": "requires_credentials", "hosts": ["x.com", "twitter.com"],
     "detail": "Needs X API credentials (not configured). Public pages may expose a preview image."},
    {"id": "instagram", "name": "Instagram", "category": "social", "status": "requires_credentials", "hosts": ["instagram.com"],
     "detail": "Needs the Meta Graph API with app review. Most content sits behind a login and is never scraped."},
    {"id": "facebook", "name": "Facebook", "category": "social", "status": "requires_credentials", "hosts": ["facebook.com", "fb.watch"],
     "detail": "Needs the Meta Graph API with app review. Private content is out of scope."},
    {"id": "tiktok", "name": "TikTok", "category": "social", "status": "requires_credentials", "hosts": ["tiktok.com"],
     "detail": "Needs TikTok Research/Display API access. Public pages may expose a preview image."},
    {"id": "linkedin", "name": "LinkedIn", "category": "social", "status": "requires_credentials", "hosts": ["linkedin.com"],
     "detail": "LinkedIn content is not available to third-party analysis without partner API access."},
    {"id": "reddit", "name": "Reddit", "category": "social", "status": "limited", "hosts": ["reddit.com", "redd.it"],
     "detail": "Public posts with direct media links (i.redd.it) can be scanned. The Data API needs credentials."},
    {"id": "email_alerts", "name": "Email alerts", "category": "alerts", "status": "requires_credentials",
     "detail": "Set DS_SMTP_* to enable."},
    {"id": "siem_webhook", "name": "SIEM / incident webhooks", "category": "enterprise", "status": "planned",
     "detail": "Phase 5: Splunk, Sentinel and generic webhook export."},
    {"id": "identity_monitoring", "name": "Consent-based identity monitoring", "category": "identity", "status": "planned",
     "detail": "Phase 4: watchlists of user-submitted URLs and consented reference enrollment."},
]


def platform_for_host(host: str) -> dict | None:
    host = host.lower()
    for p in PLATFORMS:
        for h in p.get("hosts", []):
            if host == h or host.endswith("." + h):
                return p
    return None


def integration_status() -> list[dict]:
    s = get_settings()
    out = []
    for p in PLATFORMS:
        p = dict(p)
        p.pop("hosts", None)
        if p["id"] == "email_alerts" and s.smtp_host and s.smtp_from:
            p["status"] = "operational"
            p["detail"] = "SMTP configured."
        if p["id"] == "upload" and shutil.which("ffmpeg"):
            p["detail"] = "Images, video and audio, including MP3/M4A/OGG/FLAC (ffmpeg available)."
        out.append(p)
    return out
