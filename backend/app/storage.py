"""Local object storage. Originals and derived evidence are kept in separate trees,
under random names, outside any web root. Swap for Azure Blob/S3 by reimplementing
these functions."""
import hashlib
import secrets
import shutil
from pathlib import Path

from .config import get_settings


def _root() -> Path:
    root = get_settings().storage_dir.resolve()
    (root / "originals").mkdir(parents=True, exist_ok=True)
    (root / "derived").mkdir(parents=True, exist_ok=True)
    return root


def save_original(data: bytes) -> tuple[str, str]:
    """Store bytes; returns (relative storage path, sha256)."""
    sha = hashlib.sha256(data).hexdigest()
    rel = f"originals/{secrets.token_hex(16)}.bin"
    path = _root() / rel
    path.write_bytes(data)
    return rel, sha


def read_original(rel: str) -> bytes:
    return _safe(rel).read_bytes()


def original_path(rel: str) -> Path:
    return _safe(rel)


def delete_original(rel: str | None) -> None:
    if rel:
        _safe(rel).unlink(missing_ok=True)


def derived_dir(analysis_id: str) -> Path:
    d = _root() / "derived" / analysis_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def derived_file(analysis_id: str, name: str) -> Path | None:
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    p = _root() / "derived" / analysis_id / name
    return p if p.is_file() else None


def delete_derived(analysis_id: str) -> None:
    shutil.rmtree(_root() / "derived" / analysis_id, ignore_errors=True)


def _safe(rel: str) -> Path:
    root = _root()
    p = (root / rel).resolve()
    if root not in p.parents:
        raise ValueError("path escapes storage root")
    return p
