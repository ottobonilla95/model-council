import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from parallax import accounts, auth, config, storage
from parallax.app import app
from parallax.schemas import RunRequest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-only")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-only-session-secret-at-least-32-characters")
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")
    monkeypatch.setenv("PARALLAX_OWNER_EMAIL", "owner@gmail.com")
    monkeypatch.setenv("PARALLAX_ALLOW_SIGNUP", "1")
    with TestClient(app) as client:
        yield client


def google(email="one@gmail.com", sub="google-one", **extra):
    return accounts.from_google({"sub": sub, "email": email, "name": "Example User", "email_verified": True, **extra})


def sign_in(client, user):
    token = accounts.new_session(user["id"])
    client.cookies.set(auth.COOKIE, token)
    client.headers["X-CSRF-Token"] = accounts.csrf_token(token)
    return token


def body(**extra):
    return {"question": "Private question", "models": ["test/a", "test/b"], "judge": "test/c", "demo": True, **extra}


def test_anonymous_and_missing_configuration_fail_closed(client, monkeypatch):
    assert client.get("/api/auth/me").json()["user"] is None
    for url in ("/api/config", "/api/sessions", "/api/models", "/api/runs/missing", "/api/admin/users"):
        assert client.get(url).status_code == 401
    assert client.post("/api/runs", json=body()).status_code == 401
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET")
    assert client.get("/api/sessions").status_code == 503


def test_user_cannot_read_export_stream_append_or_cancel_another_users_chat(client):
    one, two = google(), google("two@gmail.com", "google-two")
    request = RunRequest(**body(demo=False))
    run_id, session_id = storage.create_run(request, one["id"])
    storage.finish(run_id, "completed", {"mode": "chat", "answer": "ONLY ONE CAN SEE THIS"})
    storage.event(run_id, {"type": "chat_done", "answer": "ONLY ONE CAN SEE THIS"})
    sign_in(client, two)
    assert client.get("/api/sessions").json() == []
    for url in (f"/api/sessions/{session_id}", f"/api/runs/{run_id}", f"/api/runs/{run_id}/export", f"/api/runs/{run_id}/events"):
        response = client.get(url)
        assert response.status_code == 404
        assert "ONLY ONE" not in response.text
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 404
    assert client.post("/api/runs", json=body(session_id=session_id)).status_code == 404
    with pytest.raises(storage.OwnershipError):
        storage.create_run(RunRequest(**body(session_id=session_id)), two["id"])
    sign_in(client, one)
    assert client.get("/api/sessions").json()[0]["id"] == session_id
    assert client.get(f"/api/runs/{run_id}/export").json()["result"]["answer"] == "ONLY ONE CAN SEE THIS"


def test_legacy_chats_stay_out_of_signed_in_history(client):
    legacy_run, legacy = storage.create_run(RunRequest(**body()))
    owner = google("owner@gmail.com", "owner-sub")
    sign_in(client, owner)
    assert client.get("/api/sessions").json() == []

    _, current = storage.create_run(RunRequest(**body()), owner["id"])
    # Simulate the previous release assigning the anonymous chat to the owner.
    with storage.connection() as db:
        storage.query(db, "UPDATE sessions SET owner_id=? WHERE id=?", (owner["id"], legacy))
    storage.init()
    google("owner@gmail.com", "owner-sub")
    assert [row["id"] for row in client.get("/api/sessions").json()] == [current]
    assert client.get(f"/api/sessions/{legacy}").status_code == 404
    assert client.get(f"/api/runs/{legacy_run}/export").status_code == 404
    assert storage.owns_session(legacy, None)


def test_admin_create_user_verified_link_disable_revoke_and_role_protection(client):
    owner = google("owner@gmail.com", "owner-sub")
    sign_in(client, owner)
    response = client.post("/api/admin/users", json={"email": "new@gmail.com", "name": "New person", "role": "admin"})
    assert response.status_code == 201
    invited = response.json()
    assert invited["role"] == "user"
    assert client.post("/api/admin/users", json={"email": "NEW@gmail.com"}).status_code == 409
    linked = google("new@gmail.com", "new-sub")
    assert linked["id"] == invited["id"]
    assert linked["name"] == "New person"
    user_token = accounts.new_session(linked["id"])
    running_id, _ = storage.create_run(RunRequest(**body()), linked["id"])
    assert client.patch(f"/api/admin/users/{owner['id']}", json={"role": "user", "active": False}).status_code == 400
    assert client.patch(f"/api/admin/users/{linked['id']}", json={"role": "user", "active": False}).status_code == 200
    assert accounts.session_user(user_token) is None
    assert storage.get_run(running_id)["status"] == "cancelled"
    with pytest.raises(ValueError, match="disabled"):
        google("new@gmail.com", "new-sub")
    client.patch(f"/api/admin/users/{linked['id']}", json={"role": "user", "active": True})
    assert accounts.session_user(user_token) is None
    sign_in(client, google("new@gmail.com", "new-sub"))
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/admin/users", json={"email": "another@gmail.com"}).status_code == 403
    assert client.post("/api/settings", json={"openrouter": "replace-key"}).status_code == 403
    assert client.post("/api/settings", json={}).status_code == 200


def test_expiry_logout_csrf_and_cookie_forgery(client):
    user = google()
    token = sign_in(client, user)
    assert client.get("/api/auth/me").json()["csrf_token"] == accounts.csrf_token(token)
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = "forged"
    assert client.post("/api/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = accounts.csrf_token(token)
    assert client.post("/api/auth/logout").status_code == 200
    assert accounts.session_user(token) is None
    token = sign_in(client, user)
    with storage.connection() as db:
        storage.query(db, "UPDATE login_sessions SET expires=?", (time.time() - 1,))
    assert client.get("/api/sessions").status_code == 401
    client.cookies.set(auth.COOKIE, token + "tampered")
    assert client.get("/api/sessions").status_code == 401
    with storage.connection() as db:
        saved = dict(storage.query(db, "SELECT * FROM login_sessions").fetchone())
    assert token not in str(saved)


def test_verified_email_required_and_disabled_signup_can_use_precreated_account(client, monkeypatch):
    with pytest.raises(ValueError, match="verify"):
        google(email_verified=False)
    with pytest.raises(ValueError, match="Gmail"):
        google("person@example.com", "workspace")
    workspace = google("person@example.com", "workspace", hd="example.com")
    assert workspace["email"] == "person@example.com"
    monkeypatch.setenv("PARALLAX_ALLOW_SIGNUP", "0")
    with pytest.raises(ValueError, match="create your account"):
        google("invited@gmail.com", "invite")
    created = accounts.create_user("invited@gmail.com", "Invited")
    assert google("invited@gmail.com", "invite")["id"] == created["id"]


def test_oauth_failure_never_creates_session_or_exposes_provider_error(client, monkeypatch):
    monkeypatch.setattr(auth.oauth.google, "authorize_access_token", AsyncMock(side_effect=RuntimeError("private-provider-secret")))
    response = client.get("/auth/google/callback?code=untrusted&state=bad", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/?auth_error=signin"
    assert auth.COOKIE not in response.cookies
    assert "private-provider-secret" not in response.text


def test_oidc_callback_sets_http_only_cookie_and_minimal_me_response(client, monkeypatch):
    monkeypatch.setattr(
        auth.oauth.google,
        "authorize_access_token",
        AsyncMock(
            return_value={
                "userinfo": {"sub": "valid-sub", "email": "one@gmail.com", "name": "One", "email_verified": True},
                "access_token": "google-token-never-stored",
            }
        ),
    )
    response = client.get("/auth/google/callback", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    me = client.get("/api/auth/me")
    assert me.json()["user"]["email"] == "one@gmail.com"
    assert "google-token" not in me.text
    assert "google_sub" not in me.text
