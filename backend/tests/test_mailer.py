import smtplib

import pytest

from app import mailer
from app.config import get_settings

from .conftest import _register_and_login, new_email

API = "/api/v1"


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail_login = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.ssl = host, port, context is not None and self.__class__.implicit
        self.calls = []
        self.sent = []
        FakeSMTP.instances.append(self)

    implicit = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append("login")
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    def send_message(self, msg):
        self.sent.append(msg)


class FakeSMTPSSL(FakeSMTP):
    implicit = True


@pytest.fixture
def smtp(monkeypatch):
    s = get_settings()
    saved = (s.smtp_host, s.smtp_port, s.smtp_from, s.smtp_user, s.smtp_password)
    s.smtp_host, s.smtp_port, s.smtp_from = "smtp.example.com", 587, "DeepShield <no-reply@example.com>"
    s.smtp_user, s.smtp_password = "no-reply@example.com", "app-password"
    FakeSMTP.instances, FakeSMTP.fail_login = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    yield s
    s.smtp_host, s.smtp_port, s.smtp_from, s.smtp_user, s.smtp_password = saved


def test_starttls_delivery(smtp):
    res = mailer.send("someone@example.com", "Hello", "Body")
    assert res.ok and res.mode == "smtp"
    conn = FakeSMTP.instances[-1]
    assert conn.calls == ["starttls", "login"] and not conn.ssl
    assert conn.sent[0]["To"] == "someone@example.com" and "Hello" in conn.sent[0]["Subject"]


def test_implicit_tls_on_465(smtp):
    smtp.smtp_port = 465
    assert mailer.send("someone@example.com", "Hi", "Body").ok
    conn = FakeSMTP.instances[-1]
    assert conn.ssl and conn.calls == ["login"]  # no STARTTLS on an already-encrypted connection


def test_auth_failure_is_reported(smtp):
    FakeSMTP.fail_login = True
    res = mailer.send("someone@example.com", "Hi", "Body")
    assert not res.ok and "App Password" in res.error


def test_resend_verification_surfaces_failure(client, smtp):
    u = _register_and_login(client, new_email())  # its verification email goes through the fake SMTP
    assert FakeSMTP.instances, "verification email should go through SMTP when configured"
    me = client.get(f"{API}/auth/me", headers=u["headers"]).json()
    assert me["email_delivery"] == "smtp" and not me["email_verified"]
    FakeSMTP.fail_login = True
    r = client.post(f"{API}/auth/resend-verification", headers=u["headers"])
    assert r.status_code == 502 and "App Password" in r.json()["detail"]


def test_owner_test_email(client, owner, smtp):
    r = client.post(f"{API}/admin/email/test", headers=owner["headers"]).json()
    assert r["ok"] and r["delivery"] == "smtp" and r["to"] == owner["email"]


def test_outbox_mode_is_reported(client, owner):
    st = client.get(f"{API}/admin/email", headers=owner["headers"]).json()
    assert st["delivery"] == "outbox" and st["outbox_dir"]
