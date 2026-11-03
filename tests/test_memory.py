from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from parallax import accounts, auth, config, memory, storage
from parallax.app import app
from parallax.engine import execute_run
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


def user(client, email="one@gmail.com"):
    u = accounts.from_google({"sub": email, "email": email, "email_verified": True, "name": "Someone"})
    token = accounts.new_session(u["id"])
    client.cookies.set(auth.COOKIE, token)
    client.headers["X-CSRF-Token"] = accounts.csrf_token(token)
    return u


def request(question="I live in Stockholm and prefer trains.", **kwargs):
    return RunRequest(question=question, models=["test/one", "test/two"], judge="test/judge", **kwargs)


def learned(text="The user lives in Stockholm.", evidence="I live in Stockholm", replaces_id=None):
    return [{"text": text, "evidence": evidence, "replaces_id": replaces_id}]


def test_authenticated_settings_memory_crud_and_account_isolation(client):
    assert client.get("/api/me/settings").status_code == 401
    one = user(client)
    p = client.get("/api/me/settings").json()
    assert p["settings"]["memory_enabled"] and p["settings"]["auto_memory"]
    assert client.put("/api/me/settings", json={"timezone": "Fake/Zone"}).status_code == 422
    prefs = {"display_name": "Otto", "timezone": "Europe/Stockholm", "instructions": "Use metric units."}
    assert client.put("/api/me/settings", json=prefs).status_code == 200
    response = client.post("/api/me/memories", json={"text": "I prefer trains."})
    assert response.status_code == 201
    mid = response.json()["memories"][0]["id"]
    # Even an administrator cannot pass someone else's user ID to these endpoints.
    user(client, "owner@gmail.com")
    assert not client.get("/api/me/settings").json()["memories"]
    assert client.patch(f"/api/me/memories/{mid}", json={"text": "Stolen"}).status_code == 404
    assert client.delete(f"/api/me/memories/{mid}").status_code == 404
    assert client.get("/api/me/settings?user_id=" + one["id"]).json()["settings"]["display_name"] == ""
    user(client)
    assert client.get("/api/me/settings").json()["settings"]["display_name"] == "Otto"
    assert (
        client.patch(f"/api/me/memories/{mid}", json={"text": "I prefer quiet trains."}).json()["memories"][0]["text"]
        == "I prefer quiet trains."
    )
    assert client.delete(f"/api/me/memories/{mid}").json()["memories"] == []
    assert client.post("/api/me/memories", json={"text": "  "}).status_code == 422
    client.post("/api/me/memories", json={"text": "Something"})
    assert client.delete("/api/me/memories").json()["memories"] == []
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/me/memories", json={"text": "forged"}).status_code == 403


def test_memory_survives_restart_and_is_present_in_new_chat_but_not_when_disabled(client):
    u = user(client)
    memory.write(u["id"], "The user prefers trains.")
    memory.save_settings(u["id"], memory.Preferences(display_name="Otto", instructions="Use metric units.", timezone="America/New_York"))
    storage.init()
    run_id, _ = storage.create_run(request("Where should I go?"), u["id"])
    personalized = memory.personalize(request("Where should I go?"), memory.for_run(run_id))
    assert "prefers trains" in personalized.context and "metric units" in personalized.context and "Otto" in personalized.context
    assert personalized.timezone == "America/New_York"
    # Personal context is resolved on the worker, never copied into stored/exported requests.
    assert "prefers trains" not in str(storage.get_run(run_id)["request"])
    memory.save_settings(u["id"], memory.Preferences(memory_enabled=False))
    assert "prefers trains" not in memory.personalize(request(), memory.for_run(run_id)).context
    assert len(memory.get(u["id"])["memories"]) == 1


def test_evidenced_learning_retry_deduplication_and_corrections(client):
    u = user(client)
    rid, _ = storage.create_run(request(), u["id"])
    snapshot = memory.for_run(rid)
    assert memory.commit(rid, snapshot, learned()) == 1
    assert memory.commit(rid, memory.for_run(rid), learned()) == 0
    mid = memory.get(u["id"])["memories"][0]["id"]
    storage.finish(rid, "completed")
    rid, _ = storage.create_run(request("I now live in Gothenburg."), u["id"])
    assert memory.commit(rid, memory.for_run(rid), learned("The user lives in Gothenburg.", "I now live in Gothenburg", mid)) == 1
    assert len(memory.get(u["id"])["memories"]) == 1
    assert "Gothenburg" in memory.get(u["id"])["memories"][0]["text"]


@pytest.mark.parametrize("change", ["forget", "disable", "pause", "edit", "cancel", "lease"])
def test_inflight_learning_cannot_undo_user_changes_or_write_after_cancellation(client, change):
    u = user(client)
    memory.write(u["id"], "My existing preference.")
    rid, _ = storage.create_run(request(), u["id"])
    snapshot = memory.for_run(rid)
    token = None
    if change == "forget":
        memory.forget(u["id"])
    elif change == "disable":
        memory.save_settings(u["id"], memory.Preferences(memory_enabled=False))
    elif change == "pause":
        memory.save_settings(u["id"], memory.Preferences(auto_memory=False))
    elif change == "edit":
        memory.write(u["id"], "A manually corrected preference.", snapshot["memories"][0]["id"])
    elif change == "cancel":
        storage.finish(rid, "cancelled")
    else:
        storage.claim(rid, "current-worker")
        token = "stale-worker"
    assert memory.commit(rid, snapshot, learned(), token) == 0
    assert all("Stockholm" not in m["text"] for m in memory.get(u["id"])["memories"])


def test_invalid_evidence_secrets_cross_user_replacements_and_manual_edits_are_rejected(client):
    one = user(client)
    manual = memory.write(one["id"], "I prefer planes.")["memories"][0]
    two = user(client, "two@gmail.com")
    foreign = memory.write(two["id"], "I prefer boats.")["memories"][0]
    rid, _ = storage.create_run(request(), one["id"])
    bad = [
        *learned("The user likes boats.", "not in message"),
        *learned("Their API key is sk-or-v1-1234567890abcdefgh"),
        *learned(replaces_id=manual["id"]),
        *learned(replaces_id=foreign["id"]),
    ]
    assert memory.commit(rid, memory.for_run(rid), bad) == 0
    assert memory.get(one["id"])["memories"][0]["text"] == "I prefer planes."


def test_capacity_never_silently_evicts_manual_memories(client, monkeypatch):
    u = user(client)
    monkeypatch.setattr(memory, "MAX_MEMORIES", 2)
    memory.write(u["id"], "One")
    memory.write(u["id"], "Two")
    assert client.post("/api/me/memories", json={"text": "Three"}).status_code == 409
    rid, _ = storage.create_run(request(), u["id"])
    assert memory.commit(rid, memory.for_run(rid), learned()) == 0
    assert {m["text"] for m in memory.get(u["id"])["memories"]} == {"One", "Two"}


@pytest.mark.asyncio
async def test_extractor_has_only_user_message_and_bounded_account_memory_and_skips_greetings(client):
    u = user(client)
    rid, _ = storage.create_run(request(), u["id"])
    snapshot = memory.for_run(rid)
    result = AIMessage(content="", tool_calls=[{"id": "m", "name": "save_memories", "args": {"changes": learned()}}])
    model = AsyncMock()
    model.bind_tools = lambda *args, **kwargs: model
    model.ainvoke.return_value = result
    assert await memory.extract("hey", snapshot, lambda *_: pytest.fail("Greeting must not call extractor"), "test/model", "key") == []
    assert await memory.extract(request().question, snapshot, lambda *_: model, "test/model", "key") == learned()
    sent = model.ainvoke.call_args.args[0]
    assert "latest_message" in sent[1]["content"]
    assert "assistant" not in sent[1]["content"]


@pytest.mark.asyncio
async def test_live_chat_learns_then_recalls_across_sessions_and_failure_does_not_break_reply(client, monkeypatch):
    u = user(client)
    extract = AsyncMock(return_value=learned())
    monkeypatch.setattr(memory, "extract", extract)

    async def reply(req, history, *args):
        if req.question == "Where do I live?":
            assert not history and "Stockholm" in req.context
        return {"mode": "chat", "answer": "A real response", "model": req.chat_model}

    monkeypatch.setattr("parallax.engine.respond", reply)
    first = request()
    rid, _ = storage.create_run(first, u["id"])
    await execute_run(first, rid, {"openrouter": "test", "tavily": ""}, {})
    assert storage.get_run(rid)["status"] == "completed"
    assert any(e["payload"]["type"] == "memory_saved" for e in storage.events(rid))
    assert len(memory.get(u["id"])["memories"]) == 1
    second = request("Where do I live?")
    rid, _ = storage.create_run(second, u["id"])
    extract.side_effect = RuntimeError("secret-provider-error")
    await execute_run(second, rid, {"openrouter": "test", "tavily": ""}, {})
    assert storage.get_run(rid)["status"] == "completed"
    assert "secret-provider-error" not in str(storage.events(rid))
    assert any(e["payload"]["type"] == "memory_unavailable" for e in storage.events(rid))
    memory.save_settings(u["id"], memory.Preferences(auto_memory=False))
    extract.reset_mock()
    rid, _ = storage.create_run(request("No learning on this message."), u["id"])
    await execute_run(request("No learning on this message."), rid, {"openrouter": "test", "tavily": ""}, {})
    extract.assert_not_called()
