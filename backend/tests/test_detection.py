import socket

import pytest

from app.detection.base import DetectorReport, Signal
from app.detection.ensemble import assess
from app.detection.sniff import sniff
from app.detection.web import WebImpersonationDetector, parse_page, registrable_domain
from app.netguard import BlockedDestination, resolve_checked, validate_url


def rep(name, *signals, calibrated=False, score=None, thresholds=None, facts=None):
    return DetectorReport(name=name, version="t", status="ok", signals=list(signals), calibrated=calibrated,
                          score=score, thresholds=thresholds, facts=facts or {})


def sig(det, strength, direction, cat=None):
    return Signal(det, f"{det}-{strength}", "t", strength, direction, "d", category=cat)


def test_only_weak_heuristics_is_uncertain():
    out = assess("image", [rep("ela", sig("ela", "weak", "manipulated"))])
    assert out["classification"] == "uncertain"
    assert out["reliability"] == "low" and out["likelihood"] is None


def test_two_weak_from_different_detectors_is_potential():
    out = assess("image", [rep("a", sig("a", "weak", "manipulated")), rep("b", sig("b", "weak", "manipulated"))])
    assert out["classification"] == "potentially_manipulated"


def test_high_risk_requires_independent_detectors():
    single = assess("image", [rep("a", sig("a", "strong", "manipulated"), sig("a", "moderate", "manipulated"))])
    assert single["classification"] == "potentially_manipulated"
    multi = assess("image", [rep("a", sig("a", "moderate", "manipulated")), rep("b", sig("b", "strong", "manipulated"))])
    assert multi["classification"] == "high_risk"


def test_declared_synthetic_is_not_high_risk():
    out = assess("image", [rep("meta", sig("meta", "strong", "synthetic", "ai_generated_declared"))])
    assert out["synthetic_origin"] == "declared"
    assert out["classification"] == "uncertain"


def test_likely_authentic_needs_strong_evidence():
    out = assess("image", [rep("content_credentials", sig("content_credentials", "strong", "authentic"),
                               facts={"verified": True})])
    assert out["classification"] == "likely_authentic"
    assert out["reliability"] == "medium"
    cal = assess("image", [rep("ml", calibrated=True, score=0.05, thresholds={"low": 0.2, "high": 0.8})])
    assert cal["classification"] == "likely_authentic" and cal["likelihood"] == 0.05


def test_sniff_magic_bytes():
    assert sniff(b"\xff\xd8\xff\xe0" + b"\0" * 20).mime == "image/jpeg"
    assert sniff(b"RIFF\0\0\0\0WAVEfmt ").kind == "audio"
    assert sniff(b"\0\0\0\x18ftypqt  \0\0").mime == "video/quicktime"
    assert sniff(b"\0\0\0\x18ftypheic\0\0").supported is False
    assert sniff(b"MZ\x90\0") is None


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.5/", "http://[::1]/", "http://169.254.169.254/",
                                 "gopher://example.com/", "http://0.0.0.0/", "http://[::ffff:127.0.0.1]/"])
def test_validate_url_blocks(url):
    with pytest.raises(BlockedDestination):
        validate_url(url)


def test_resolve_blocks_localhost_names():
    with pytest.raises(BlockedDestination):
        resolve_checked("localhost", 80)


def test_resolve_allows_public(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.215.14", 80))])
    assert resolve_checked("example.com", 80) == "93.184.215.14"


def test_dns_rebinding_any_private_answer_blocks(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.215.14", 80)),
                                                                 (2, 1, 6, "", ("10.1.2.3", 80))])
    with pytest.raises(BlockedDestination):
        resolve_checked("evil.example", 80)


def _web(url, html):
    from pathlib import Path

    from app.detection.base import MediaContext
    ctx = MediaContext("t", html.encode(), "html", "text/html", Path("."), Path("."), source_url=url)
    return WebImpersonationDetector().run(ctx)


def test_web_lookalike_and_official():
    bad = _web("https://paypa1.com/login", "<title>Sign in</title>")
    assert any(s.id == "lookalike_domain" for s in bad.signals)
    sub = _web("https://paypal.com.secure-check.xyz/", "<title>x</title>")
    assert any(s.id == "lookalike_domain" for s in sub.signals)
    ok = _web("https://www.paypal.com/signin", "<title>PayPal</title><input type=password>")
    assert not ok.signals
    puny = _web("https://xn--pypal-4ve.com/", "<title>x</title>")
    assert any(s.id == "punycode" for s in puny.signals)


def test_registrable_domain():
    assert registrable_domain("a.b.example.co.uk") == "example.co.uk"
    assert registrable_domain("www.example.com") == "example.com"


def test_page_media_discovery():
    p = parse_page(b"<meta property='og:image' content='/a.jpg'><img src='b.png'>", "https://site.test/x/")
    from app.detection.web import discover_media
    assert discover_media(p)[0] == ("image", "https://site.test/a.jpg")
