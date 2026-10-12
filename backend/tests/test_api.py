import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from app.config import get_settings

from .conftest import jpeg_bytes, make_user, photo_like, wait_done, wav_bytes

API = "/api/v1"


def upload(client, headers, data: bytes, name: str):
    return client.post(f"{API}/analyses/upload", headers=headers, files={"file": (name, data, "application/octet-stream")})


def test_register_login_and_roles(client):
    u = make_user(client)
    me = client.get(f"{API}/auth/me", headers=u["headers"]).json()
    assert me["email"] == u["email"] and me["role"] in ("admin", "analyst")
    assert client.get(f"{API}/auth/me").status_code == 401
    bad = client.post(f"{API}/auth/login", json={"email": u["email"], "password": "wrong-password-123"})
    assert bad.status_code == 401
    terms = client.post(f"{API}/auth/register", json={"email": "x@example.com", "password": "abcdefghijk1", "accept_terms": False})
    assert terms.status_code == 400


def test_non_admin_cannot_read_audit(client):
    make_user(client)  # ensure an admin exists already
    u = make_user(client)
    assert client.get(f"{API}/admin/audit", headers=u["headers"]).status_code == 403


def test_plain_photo_is_not_flagged_high(client, user):
    r = upload(client, user["headers"], jpeg_bytes(photo_like()), "photo.jpg")
    assert r.status_code == 202
    res = wait_done(client, user["headers"], r.json()["id"])
    assert res["status"] == "completed", res
    a = res["result"]["assessment"]
    assert a["classification"] in ("uncertain", "potentially_manipulated")
    assert a["likelihood"] is None and a["likelihood_calibrated"] is False
    assert a["reliability"] == "low"
    names = {d["name"]: d["status"] for d in res["result"]["detectors"]}
    assert names["ml_image"] == "unavailable"  # never faked
    assert names["error_level_analysis"] == "ok"
    assert any("No calibrated deep-learning detector" in lim for lim in res["result"]["limitations"])
    ev = client.get(f"{API}/analyses/{res['id']}/evidence/ela.png", headers=user["headers"])
    assert ev.status_code == 200 and ev.headers["content-type"] == "image/png"


def test_declared_ai_png_is_synthetic_not_high_risk(client, user):
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a portrait, Steps: 30, Sampler: DPM++, Model: sdxl")
    buf = io.BytesIO()
    photo_like(seed=3).save(buf, "PNG", pnginfo=info)
    res = wait_done(client, user["headers"], upload(client, user["headers"], buf.getvalue(), "gen.png").json()["id"])
    a = res["result"]["assessment"]
    assert a["synthetic_origin"] == "declared"
    assert a["classification"] != "high_risk"
    assert "ai_generated_declared" in a["categories"]


def test_face_app_and_edit_metadata_flags(client, user):
    exif = Image.Exif()
    exif[0x0131] = "FaceApp 11.2"
    exif[0x0132] = "2026:01:02 10:00:00"
    res = wait_done(client, user["headers"],
                    upload(client, user["headers"], jpeg_bytes(photo_like(seed=5), exif=exif), "selfie.jpg").json()["id"])
    a = res["result"]["assessment"]
    assert a["classification"] in ("potentially_manipulated", "high_risk")
    assert any(s["id"] == "face_app_metadata" for s in res["result"]["signals"])


def test_audio_wav(client, user):
    res = wait_done(client, user["headers"], upload(client, user["headers"], wav_bytes(), "voice.wav").json()["id"])
    assert res["status"] == "completed"
    ids = {s["id"] for s in res["result"]["signals"]}
    assert "digital_silence" in ids
    assert res["result"]["assessment"]["classification"] != "high_risk"
    assert any(e["name"] == "spectrogram.png" for e in res["result"]["evidence"])


def test_video_mp4(client, user, tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "clip.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 15, (160, 120))
    for i in range(45):
        frame = np.full((120, 160, 3), (i * 5) % 255, np.uint8)
        cv2.rectangle(frame, (10 + i, 30), (50 + i, 70), (0, 0, 255), -1)
        vw.write(frame)
    vw.release()
    res = wait_done(client, user["headers"], upload(client, user["headers"], path.read_bytes(), "clip.mp4").json()["id"])
    assert res["status"] == "completed", res
    assert res["kind"] == "video"
    frames = [e for e in res["result"]["evidence"] if e["kind"] == "frame"]
    assert frames and frames[0]["timestamp_s"] is not None
    av = next(d for d in res["result"]["detectors"] if d["name"] == "av_sync")
    assert av["status"] == "unavailable"


def test_rejects_unsupported_and_spoofed_types(client, user):
    r = upload(client, user["headers"], b"MZ\x90\x00 this is an exe" * 10, "image.jpg")
    assert r.status_code == 415
    r = upload(client, user["headers"], b"<script>alert(1)</script>", "x.png")
    assert r.status_code == 415


def test_reports_signed_links(client, user):
    aid = upload(client, user["headers"], jpeg_bytes(photo_like(seed=9)), "r.jpg").json()["id"]
    wait_done(client, user["headers"], aid)
    for fmt, ctype in (("pdf", "application/pdf"), ("json", "application/json")):
        link = client.post(f"{API}/analyses/{aid}/report-link", headers=user["headers"], json={"format": fmt}).json()
        r = client.get(link["url"])
        assert r.status_code == 200 and r.headers["content-type"].startswith(ctype)
        if fmt == "pdf":
            assert r.content[:4] == b"%PDF"
        else:
            body = r.json()
            assert body["analysis_id"] == aid and "disclaimer" in body
    tampered = link["url"][:-3] + ("AAA" if not link["url"].endswith("AAA") else "BBB")
    assert client.get(tampered).status_code == 403


def test_isolation_between_users(client):
    a, b = make_user(client), make_user(client)
    aid = upload(client, a["headers"], jpeg_bytes(photo_like(seed=11)), "a.jpg").json()["id"]
    wait_done(client, a["headers"], aid)
    assert client.get(f"{API}/analyses/{aid}", headers=b["headers"]).status_code == 404
    assert client.post(f"{API}/analyses/{aid}/report-link", headers=b["headers"], json={"format": "pdf"}).status_code == 404
    assert client.get(f"{API}/analyses/{aid}/evidence/ela.png", headers=b["headers"]).status_code == 404


def test_cases_alerts_and_delete(client, user):
    exif = Image.Exif()
    exif[0x0131] = "DeepFaceLab"
    aid = upload(client, user["headers"], jpeg_bytes(photo_like(seed=13), exif=exif), "c.jpg").json()["id"]
    wait_done(client, user["headers"], aid)
    alerts = client.get(f"{API}/alerts", headers=user["headers"]).json()
    assert any(al["analysis_id"] == aid for al in alerts)
    al = next(al for al in alerts if al["analysis_id"] == aid)
    assert client.patch(f"{API}/alerts/{al['id']}", headers=user["headers"], json={"state": "dismissed"}).json()["state"] == "dismissed"

    case = client.post(f"{API}/cases", headers=user["headers"], json={"title": "Fake CEO video", "analysis_id": aid}).json()
    assert case["items"][0]["id"] == aid
    case = client.post(f"{API}/cases/{case['id']}/notes", headers=user["headers"], json={"body": "Reported to platform"}).json()
    assert case["notes"][0]["body"] == "Reported to platform"
    case = client.patch(f"{API}/cases/{case['id']}", headers=user["headers"], json={"status": "reported"}).json()
    assert case["status"] == "reported"

    summary = client.get(f"{API}/dashboard/summary", headers=user["headers"]).json()
    assert summary["total"] >= 1 and summary["open_cases"] == 0

    assert client.delete(f"{API}/analyses/{aid}", headers=user["headers"]).status_code == 204
    assert client.get(f"{API}/analyses/{aid}", headers=user["headers"]).status_code == 404


def test_api_tokens(client, user):
    created = client.post(f"{API}/auth/tokens", headers=user["headers"], json={"name": "Chrome"}).json()
    tok_headers = {"Authorization": f"Bearer {created['token']}"}
    assert client.get(f"{API}/auth/me", headers=tok_headers).status_code == 200
    # tokens cannot mint more tokens
    assert client.post(f"{API}/auth/tokens", headers=tok_headers, json={"name": "x"}).status_code == 403
    client.delete(f"{API}/auth/tokens/{created['id']}", headers=user["headers"])
    assert client.get(f"{API}/auth/me", headers=tok_headers).status_code == 401


def test_url_scan_blocks_private_targets(client, user):
    for bad in ("http://127.0.0.1/x.jpg", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd",
                "http://example.com:8080/a.jpg", "http://user:pw@example.com/a.jpg"):
        r = client.post(f"{API}/analyses/url", headers=user["headers"], json={"url": bad})
        assert r.status_code == 400, bad


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        port = self.server.server_address[1]
        if self.path == "/login":
            body = (f"<html><head><title>PayPal - Log in</title><meta property='og:image' "
                    f"content='http://127.0.0.1:{port}/img.jpg'></head><body><p>Unusual activity. Verify your account"
                    "</p><form action='https://collector.example.net/x'><input type='password'></form></body></html>").encode()
            ctype = "text/html"
        elif self.path == "/img.jpg":
            body, ctype = jpeg_bytes(photo_like(seed=21)), "image/jpeg"
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/")
            self.end_headers()
            return
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def local_site():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = get_settings()
    s.allow_private_fetch = True
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    s.allow_private_fetch = False
    srv.shutdown()


def test_url_scan_page_with_embedded_media(client, user, local_site):
    r = client.post(f"{API}/analyses/url", headers=user["headers"], json={"url": f"{local_site}/login"})
    assert r.status_code == 202
    res = wait_done(client, user["headers"], r.json()["id"])
    assert res["status"] == "completed", res
    assert res["kind"] == "html"
    ids = {s["id"] for s in res["result"]["signals"]}
    assert "brand_credential_form" in ids
    assert res["result"]["assessment"]["classification"] in ("potentially_manipulated", "high_risk")
    emb = res["result"]["embedded_media"]
    assert emb and emb[0]["kind"] == "image"
    child = wait_done(client, user["headers"], emb[0]["analysis_id"])
    assert child["status"] == "completed" and child["kind"] == "image"
    assert child["page_url"].endswith("/login")


def test_production_mode_blocks_local_server(client, user, local_site):
    get_settings().allow_private_fetch = False
    r = client.post(f"{API}/analyses/url", headers=user["headers"], json={"url": f"{local_site}/redirect"})
    assert r.status_code == 400  # loopback address and non-standard port are rejected before any request