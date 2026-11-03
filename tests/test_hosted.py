import sqlite3
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from parallax import auth, config, storage
from parallax.app import TASKS, app
from parallax.jobs import process_run
from parallax.schemas import RunRequest


def request():
    return RunRequest(question="How should I compare evidence?", models=["test/one", "test/two"], judge="test/judge", demo=True)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)

    @contextmanager
    def test_connection():
        # Exercise hosted lifecycle behavior against an isolated, real SQL database.
        conn = sqlite3.connect(tmp_path / "hosted-test.sqlite3", timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    monkeypatch.setattr(storage, "connection", test_connection)
    storage.init()


def test_hosted_storage_and_credentials_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        storage.init()
    with pytest.raises(ValueError, match="Vercel"):
        config.save_keys({"openrouter": "secret"})
    assert not list(tmp_path.iterdir())
    assert "*.vercel.app" in config.allowed_hosts()


@pytest.mark.asyncio
async def test_queue_replay_and_cold_start_preserve_completed_run(db, monkeypatch):
    run_id, _ = storage.create_run(request())
    await process_run(run_id)
    assert storage.get_run(run_id)["status"] == "completed"
    events = storage.events(run_id)
    await process_run(run_id)
    assert storage.events(run_id) == events
    monkeypatch.setattr(config, "hosted", lambda: True)
    storage.init()
    assert storage.get_run(run_id)["status"] == "completed"


def test_lease_fencing_and_admission(db, monkeypatch):
    run_id, _ = storage.create_run(request())
    assert storage.claim(run_id, "first")
    assert not storage.claim(run_id, "second")
    storage.release(run_id, "first")
    assert storage.claim(run_id, "second")
    with pytest.raises(storage.LeaseLostError):
        storage.event(run_id, {"type": "activity"}, token="first")
    assert not storage.finish(run_id, "completed", token="first")
    assert storage.finish(run_id, "cancelled", token="second", terminal={"type": "cancelled"})
    assert not storage.finish(run_id, "completed", token="second", terminal={"type": "done"})
    assert storage.events(run_id)[-1]["payload"]["type"] == "cancelled"
    one, _ = storage.create_run(request())
    storage.create_run(request())
    with pytest.raises(storage.CapacityError):
        storage.create_run(request())
    monkeypatch.setattr(config, "hosted", lambda: True)
    storage.init()
    assert storage.get_run(one)["status"] == "running"


@pytest.mark.asyncio
async def test_queue_retry_reuses_completed_researchers(db, monkeypatch):
    from parallax.engine import ParallaxEngine

    run_id, _ = storage.create_run(request())
    original = ParallaxEngine.compare
    calls = 0

    async def crash_once(self, state):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("A worker crashed after research")
        return await original(self, state)

    monkeypatch.setattr(ParallaxEngine, "compare", crash_once)
    with pytest.raises(RuntimeError):
        await process_run(run_id)
    assert storage.get_run(run_id)["status"] == "running"
    assert len(storage.completed_reports(run_id)) == 2
    await process_run(run_id)
    assert storage.get_run(run_id)["status"] == "completed"
    assert len([e for e in storage.events(run_id) if e["payload"]["type"] == "researcher_done"]) == 2


def test_hosted_api_enqueues_and_does_not_spawn_in_memory_task(db, monkeypatch):
    monkeypatch.setattr(auth, "required", lambda: False)  # Queue behavior is isolated from browser auth here.
    queued = []

    async def enqueue(run_id):
        queued.append(run_id)

    monkeypatch.setattr("parallax.jobs.enqueue", enqueue)
    monkeypatch.setattr(config, "hosted", lambda: True)
    with TestClient(app) as client:
        response = client.post("/api/runs", json=request().model_dump())
        assert response.status_code == 201
        run_id = response.json()["run_id"]
        assert queued == [run_id]
        assert run_id not in TASKS
        assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
        assert storage.get_run(run_id)["status"] == "cancelled"
        assert client.post("/api/settings", json={"tavily": "secret"}).status_code == 403
        assert client.post("/api/settings", json={}).status_code == 200


def test_queue_publish_failure_is_visible_and_not_left_running(db, monkeypatch):
    monkeypatch.setattr(auth, "required", lambda: False)

    async def broken(_):
        raise RuntimeError("private queue failure")

    monkeypatch.setattr("parallax.jobs.enqueue", broken)
    monkeypatch.setattr(config, "hosted", lambda: True)
    with TestClient(app) as client:
        response = client.post("/api/runs", json=request().model_dump())
        assert response.status_code == 503
        saved = storage.session_runs(storage.sessions()[0]["id"])[0]
        assert saved["status"] == "failed"
        assert "private" not in str(storage.events(saved["id"]))


@pytest.mark.asyncio
async def test_cancellation_in_another_instance_cannot_be_overwritten(db):
    import asyncio

    run_id, _ = storage.create_run(request())
    task = asyncio.create_task(process_run(run_id))
    for _ in range(100):
        if storage.events(run_id):
            break
        await asyncio.sleep(0.01)
    storage.finish(run_id, "cancelled", terminal={"type": "cancelled"})
    await asyncio.wait_for(task, 6)
    assert storage.get_run(run_id)["status"] == "cancelled"
    assert not any(e["payload"]["type"] == "done" for e in storage.events(run_id))
