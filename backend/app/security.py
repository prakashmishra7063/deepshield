import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt

from .config import get_settings

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 64}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def create_access_token(user_id: int, version: int = 0) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "ver": version, "iat": now,
               "exp": now + timedelta(minutes=s.access_token_minutes), "typ": "access"}
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> tuple[int, int] | None:
    """Returns (user_id, token_version) for a valid access token."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        if payload.get("typ") != "access":
            return None
        return int(payload["sub"]), int(payload.get("ver", 0))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def new_secret_token() -> tuple[str, str]:
    """Random URL-safe token for emailed links; returns (raw, sha256 hex)."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_secret_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


API_TOKEN_PREFIX = "dsk_"


def new_api_token() -> tuple[str, str]:
    raw = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_token(raw)


def hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_report_link(analysis_id: str, user_id: int, fmt: str) -> str:
    """Short-lived HMAC-signed token that grants download of one report."""
    s = get_settings()
    body = json.dumps(
        {"a": analysis_id, "u": user_id, "f": fmt, "e": int(time.time()) + s.report_link_minutes * 60},
        separators=(",", ":"),
    ).encode()
    sig = hmac.new(s.secret_key.encode(), b"report:" + body, hashlib.sha256).digest()
    return _b64(body) + "." + _b64(sig)


def verify_report_link(token: str) -> dict | None:
    try:
        body_b64, sig_b64 = token.split(".")
        body = _unb64(body_b64)
        expected = hmac.new(get_settings().secret_key.encode(), b"report:" + body, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        data = json.loads(body)
        if data["e"] < time.time() or data["f"] not in ("pdf", "json"):
            return None
        return data
    except Exception:
        return None
