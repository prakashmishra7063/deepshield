from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DS_", env_file=".env", extra="ignore")

    env: str = "development"
    secret_key: str = "change-me-in-production-please-32+chars"
    database_url: str = "sqlite:///./data/deepshield.db"
    storage_dir: Path = Path("./data/storage")
    cors_origins: str = "http://localhost:3000"
    # Public URL of the web app, used in emails (verification, password reset, invites).
    app_url: str = "http://localhost:3100"
    product_name: str = "DeepShield AI"

    access_token_minutes: int = 60
    report_link_minutes: int = 10

    max_upload_mb: int = 100
    max_fetch_mb: int = 50
    fetch_timeout_s: float = 15.0
    max_redirects: int = 3
    # Testing only: allow fetching from private networks. Never enable in production.
    allow_private_fetch: bool = False

    retention_hours: int = 24
    worker_threads: int = 2

    rate_limit_per_minute: int = 60
    scan_rate_limit_per_hour: int = 120

    # Optional pluggable models (TorchScript). Unset = detector reports "unavailable".
    image_model_path: str | None = None
    image_model_calibration: str | None = None  # JSON file with thresholds from evaluation
    audio_model_path: str | None = None
    audio_model_calibration: str | None = None

    # Optional email alerts. Unset = email channel reported as not configured.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True  # ignored on port 465 (implicit TLS)
    # Without SMTP, emails are written here so links can be followed during development.
    outbox_dir: Path = Path("./data/outbox")
    verification_hours: int = 48
    reset_minutes: int = 60
    invite_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "production" and (s.secret_key.startswith("change-me") or len(s.secret_key) < 32):
        raise RuntimeError("DS_SECRET_KEY must be set to a random value of 32+ characters in production")
    if s.env == "production" and s.allow_private_fetch:
        raise RuntimeError("DS_ALLOW_PRIVATE_FETCH must not be enabled in production")
    return s
