import io
import os
import tempfile
import time
import wave

import numpy as np
import pytest
from PIL import Image

_tmp = tempfile.mkdtemp(prefix="deepshield-test-")
os.environ["DS_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DS_STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["DS_SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
os.environ["DS_WORKER_THREADS"] = "2"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402
from app.worker import jobs  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    limiter.reset()
    yield


_counter = [0]


def make_user(client) -> dict:
    _counter[0] += 1
    email = f"user{_counter[0]}-{time.time_ns()}@example.com"
    pw = "correct-horse-battery-9"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": pw, "accept_terms": True})
    assert r.status_code == 201, r.text
    tok = client.post("/api/v1/auth/login", json={"email": email, "password": pw}).json()["access_token"]
    return {"email": email, "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture
def user(client):
    return make_user(client)


def wait_done(client, headers, analysis_id, timeout=60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs.wait_idle(timeout=5)
        r = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()
        if r["status"] in ("completed", "failed"):
            return r
        time.sleep(0.1)
    raise AssertionError("analysis did not finish")


def photo_like(w=512, h=384, seed=0) -> Image.Image:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack([(x / w) * 200, (y / h) * 180, ((x + y) / (w + h)) * 160], axis=2)
    noise = rng.normal(0, 8, (h, w, 3))
    return Image.fromarray(np.clip(base + noise + 30, 0, 255).astype(np.uint8))


def jpeg_bytes(im: Image.Image, quality=88, exif=None) -> bytes:
    buf = io.BytesIO()
    kw = {"quality": quality}
    if exif is not None:
        kw["exif"] = exif
    im.save(buf, "JPEG", **kw)
    return buf.getvalue()


def wav_bytes(sr=48000, seconds=3.0, gaps=True) -> bytes:
    t = np.arange(int(sr * seconds)) / sr
    sig = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 3000 * t)
    if gaps:
        for k in range(5):
            s = int(sr * (0.5 + k * 0.45))
            sig[s:s + int(0.08 * sr)] = 0.0
    pcm = (sig * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()
