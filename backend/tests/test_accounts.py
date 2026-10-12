"""SaaS account features: verification, passwords, workspaces, quotas and the owner console."""
from .conftest import PASSWORD, _register_and_login, jpeg_bytes, make_user, new_email, outbox_token, photo_like, wait_done

API = "/api/v1"


def upload(client, headers, seed=0):
    return client.post(f"{API}/analyses/upload", headers=headers,
                       files={"file": ("p.jpg", jpeg_bytes(photo_like(seed=seed)), "image/jpeg")})


def active_org(client, headers) -> dict:
    return client.get(f"{API}/org", headers=headers).json()


# ---------------------------------------------------------------- verification & passwords

def test_owner_is_first_user_and_auto_verified(client, owner):
    me = client.get(f"{API}/auth/me", headers=owner["headers"]).json()
    assert me["role"] == "owner" and me["email_verified"]
    assert active_org(client, owner["headers"])["plan"]["id"] == "internal"


def test_unverified_users_cannot_scan_until_verified(client):
    u = make_user(client, verify=False)
    assert client.get(f"{API}/auth/me", headers=u["headers"]).json()["email_verified"] is False
    assert upload(client, u["headers"]).status_code == 403
    token = outbox_token(u["email"], "verify-email")
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    assert upload(client, u["headers"]).status_code == 202
    # Tokens are single use
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400


def test_forgot_and_reset_password_revokes_old_sessions(client):
    u = make_user(client)
    assert client.post(f"{API}/auth/forgot-password", json={"email": u["email"]}).status_code == 204
    # Unknown emails get the same response (no account enumeration)
    assert client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 204
    token = outbox_token(u["email"], "reset-password")
    new_pw = "brand-new-Passw0rd!"
    assert client.post(f"{API}/auth/reset-password", json={"token": token, "password": new_pw}).status_code == 204
    assert client.get(f"{API}/auth/me", headers=u["headers"]).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": u["email"], "password": PASSWORD}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": u["email"], "password": new_pw}).status_code == 200
    assert client.post(f"{API}/auth/reset-password", json={"token": token, "password": new_pw}).status_code == 400


def test_change_password_returns_new_session(client):
    u = make_user(client)
    bad = client.post(f"{API}/auth/change-password", headers=u["headers"],
                      json={"current_password": "wrong-password-x", "new_password": "another-Passw0rd"})
    assert bad.status_code == 400
    r = client.post(f"{API}/auth/change-password", headers=u["headers"],
                    json={"current_password": PASSWORD, "new_password": "another-Passw0rd"})
    assert r.status_code == 200
    assert client.get(f"{API}/auth/me", headers=u["headers"]).status_code == 401
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{API}/auth/me", headers=fresh).status_code == 200


# ---------------------------------------------------------------- quotas & credits

def test_monthly_quota_and_credits(client, owner):
    u = make_user(client)
    org = active_org(client, u["headers"])
    assert org["plan"]["id"] == "free" and org["usage"]["used"] == 0
    r = client.patch(f"{API}/admin/orgs/{org['id']}", headers=owner["headers"], json={"scan_quota_override": 1})
    assert r.status_code == 200
    assert upload(client, u["headers"], 1).status_code == 202
    blocked = upload(client, u["headers"], 2)
    assert blocked.status_code == 402 and "scans" in blocked.json()["detail"]
    client.patch(f"{API}/admin/orgs/{org['id']}", headers=owner["headers"], json={"credits_delta": 1})
    assert upload(client, u["headers"], 3).status_code == 202
    assert active_org(client, u["headers"])["usage"]["credits"] == 0
    assert upload(client, u["headers"], 4).status_code == 402


def test_plan_upload_limit(client, owner):
    u = make_user(client)
    org = active_org(client, u["headers"])
    assert org["plan"]["max_upload_mb"] == 10
    big = b"\xff\xd8\xff\xe0" + b"\0" * (11 * 1024 * 1024)
    r = client.post(f"{API}/analyses/upload", headers=u["headers"], files={"file": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413 and "Free" in r.json()["detail"]


# ---------------------------------------------------------------- team workspaces

def test_team_invites_roles_and_isolation(client, owner):
    boss = make_user(client)
    me = client.post(f"{API}/orgs", headers=boss["headers"], json={"name": "Acme Newsroom"}).json()
    team_id = me["active_org_id"]
    assert any(m["org_id"] == team_id and m["role"] == "owner" for m in me["memberships"])

    # Free plan has a single seat
    staff_email = new_email()
    r = client.post(f"{API}/org/invites", headers=boss["headers"], json={"email": staff_email})
    assert r.status_code == 402
    client.patch(f"{API}/admin/orgs/{team_id}", headers=owner["headers"], json={"plan_id": "business"})
    r = client.post(f"{API}/org/invites", headers=boss["headers"], json={"email": staff_email})
    assert r.status_code == 201

    token = outbox_token(staff_email, "invite")
    preview = client.get(f"{API}/invites/{token}").json()
    assert preview["org_name"] == "Acme Newsroom" and preview["email"] == staff_email
    # Invite tokens are bound to the invited address
    wrong = client.post(f"{API}/auth/register", json={"email": new_email(), "password": PASSWORD,
                                                      "accept_terms": True, "invite_token": token})
    assert wrong.status_code == 403
    staff = _register_and_login(client, staff_email, invite_token=token)
    staff_me = client.get(f"{API}/auth/me", headers=staff["headers"]).json()
    assert staff_me["active_org_id"] == team_id and staff_me["email_verified"]

    # Shared analyses inside the team; members can't delete others' work
    aid = upload(client, boss["headers"], 10).json()["id"]
    wait_done(client, boss["headers"], aid)
    assert client.get(f"{API}/analyses/{aid}", headers=staff["headers"]).status_code == 200
    assert client.delete(f"{API}/analyses/{aid}", headers=staff["headers"]).status_code == 403
    assert client.patch(f"{API}/org/members/{staff['id']}", headers=staff["headers"],
                        json={"role": "admin"}).status_code == 403

    # Switching to the personal workspace hides team data
    personal = next(m["org_id"] for m in staff_me["memberships"] if m["kind"] == "personal")
    client.post(f"{API}/auth/switch-org", headers=staff["headers"], json={"org_id": personal})
    assert client.get(f"{API}/analyses/{aid}", headers=staff["headers"]).status_code == 404
    # Can't switch into a workspace you don't belong to
    outsider = make_user(client)
    assert client.post(f"{API}/auth/switch-org", headers=outsider["headers"],
                       json={"org_id": team_id}).status_code == 404

    # Last owner can't leave; members can
    assert client.delete(f"{API}/org/members/{boss['id']}", headers=boss["headers"]).status_code == 409
    client.post(f"{API}/auth/switch-org", headers=staff["headers"], json={"org_id": team_id})
    assert client.delete(f"{API}/org/members/{staff['id']}", headers=staff["headers"]).status_code == 204
    assert client.get(f"{API}/analyses/{aid}", headers=staff["headers"]).status_code == 404


def test_deleting_member_keeps_team_data(client, owner):
    boss = make_user(client)
    team_id = client.post(f"{API}/orgs", headers=boss["headers"], json={"name": "Keepers"}).json()["active_org_id"]
    client.patch(f"{API}/admin/orgs/{team_id}", headers=owner["headers"], json={"plan_id": "business"})
    email = new_email()
    client.post(f"{API}/org/invites", headers=boss["headers"], json={"email": email})
    staff = _register_and_login(client, email, invite_token=outbox_token(email, "invite"))
    aid = upload(client, staff["headers"], 20).json()["id"]
    wait_done(client, staff["headers"], aid)
    r = client.request("DELETE", f"{API}/auth/me", headers=staff["headers"],
                       json={"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 204
    assert client.get(f"{API}/analyses/{aid}", headers=boss["headers"]).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401


# ---------------------------------------------------------------- owner console

def test_owner_console_access_and_suspension(client, owner):
    u = make_user(client)
    assert client.get(f"{API}/admin/overview", headers=u["headers"]).status_code == 403
    ov = client.get(f"{API}/admin/overview", headers=owner["headers"]).json()
    assert ov["users"] >= 2 and "free" in ov["by_plan"]
    users = client.get(f"{API}/admin/users", headers=owner["headers"], params={"q": u["email"]}).json()
    assert users["total"] == 1 and users["items"][0]["email"] == u["email"]

    assert client.patch(f"{API}/admin/users/{u['id']}", headers=owner["headers"],
                        json={"status": "suspended"}).status_code == 200
    assert client.get(f"{API}/auth/me", headers=u["headers"]).status_code in (401, 403)
    assert client.post(f"{API}/auth/login", json={"email": u["email"], "password": PASSWORD}).status_code == 403
    client.patch(f"{API}/admin/users/{u['id']}", headers=owner["headers"], json={"status": "active"})
    assert client.post(f"{API}/auth/login", json={"email": u["email"], "password": PASSWORD}).status_code == 200
    # Owner can't suspend themselves
    assert client.patch(f"{API}/admin/users/{owner['id']}", headers=owner["headers"],
                        json={"status": "suspended"}).status_code == 400


def test_owner_cannot_read_customer_content(client, owner):
    u = make_user(client)
    aid = upload(client, u["headers"], 30).json()["id"]
    wait_done(client, u["headers"], aid)
    assert client.get(f"{API}/analyses/{aid}", headers=owner["headers"]).status_code == 404
    assert client.get(f"{API}/analyses/{aid}/evidence/ela.png", headers=owner["headers"]).status_code == 404


def test_suspended_workspace_cannot_scan(client, owner):
    u = make_user(client)
    org_id = active_org(client, u["headers"])["id"]
    client.patch(f"{API}/admin/orgs/{org_id}", headers=owner["headers"], json={"status": "suspended"})
    assert upload(client, u["headers"]).status_code == 403
    client.patch(f"{API}/admin/orgs/{org_id}", headers=owner["headers"], json={"status": "active"})
    assert upload(client, u["headers"]).status_code == 202


def test_signups_can_be_closed(client, owner):
    client.patch(f"{API}/admin/settings", headers=owner["headers"], json={"signups_open": False})
    try:
        r = client.post(f"{API}/auth/register", json={"email": new_email(), "password": PASSWORD, "accept_terms": True})
        assert r.status_code == 403
    finally:
        client.patch(f"{API}/admin/settings", headers=owner["headers"], json={"signups_open": True})


def test_plans_management(client, owner):
    r = client.post(f"{API}/admin/plans", headers=owner["headers"], json={
        "id": "starter", "name": "Starter", "monthly_scans": 50, "max_upload_mb": 25, "max_members": 1,
        "price_monthly_cents": 500})
    assert r.status_code == 201
    public = [p["id"] for p in client.get(f"{API}/plans").json()]
    assert "starter" in public and "internal" not in public
    client.patch(f"{API}/admin/plans/starter", headers=owner["headers"], json={"public": False})
    assert "starter" not in [p["id"] for p in client.get(f"{API}/plans").json()]
    audit = client.get(f"{API}/admin/audit", headers=owner["headers"], params={"action": "admin.plan"}).json()
    assert {a["action"] for a in audit} >= {"admin.plan_create", "admin.plan_update"}
