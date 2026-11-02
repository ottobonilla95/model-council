import json
import time

import pytest
from fastapi.testclient import TestClient

from council import config, storage
from council.app import app
from council.schemas import RunRequest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with TestClient(app) as client:
        yield client


def body(**kwargs):
    return {"question": "What should I investigate?", "models": ["test/one", "test/two"], "judge": "test/judge", "demo": True, **kwargs}


def wait_done(client, run_id):
    for _ in range(100):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    pytest.fail("Demo did not complete")


def test_demo_full_round_persistence_export_and_event_replay(client):
    response = client.post("/api/runs", json=body())
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    saved = wait_done(client, run_id)
    assert saved["status"] == "completed"
    assert len(saved["result"]["reports"]) == 2
    assert "sample comparison" in saved["result"]["comparison"]["answer"]
    assert client.get("/api/sessions").json()[0]["rounds"] == 1
    exported = client.get(f"/api/runs/{run_id}/export")
    assert "attachment" in exported.headers["content-disposition"]
    assert exported.json()["result"] == saved["result"]
    last = saved["events"][-2]["id"]
    with client.stream("GET", f"/api/runs/{run_id}/events?after={last}") as stream:
        text = stream.read().decode()
    assert '"type": "done"' in text
    assert '"type": "researcher_start"' not in text


def test_missing_credentials_duplicate_models_and_bad_origin(client):
    assert client.post("/api/runs", json=body(demo=False)).status_code == 400
    assert client.post("/api/runs", json=body(models=["test/one", "test/one"])).status_code == 422
    assert client.post("/api/runs", json=body(question="  ")).status_code == 422
    assert client.post("/api/settings", json={"openrouter": "bad"}, headers={"Origin": "https://unrelated.example"}).status_code == 403
    assert not client.get("/api/sessions").json()


def test_cancel_preserves_round_and_does_not_claim_consensus(client):
    run_id = client.post("/api/runs", json=body()).json()["run_id"]
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    saved = client.get(f"/api/runs/{run_id}").json()
    assert saved["status"] == "cancelled"
    assert not saved["result"].get("comparison")
    assert saved["events"][-1]["payload"]["type"] == "cancelled"


def test_credentials_never_returned_and_saved_with_private_permissions(client):
    response = client.post("/api/settings", json={"openrouter": "secret-openrouter", "tavily": "secret-tavily"})
    assert response.json()["keys"] == {"openrouter": True, "tavily": True}
    assert "secret" not in response.text
    assert config.keys()["tavily"] == "secret-tavily"
    assert (config.DATA / "credentials.json").stat().st_mode & 0o777 == 0o600


def test_history_contains_only_user_and_own_model_and_restart_is_visible(client):
    request = RunRequest(**body(demo=False))
    run_id, session_id = storage.create_run(request)
    storage.finish(
        run_id,
        "completed",
        {
            "reports": [{"model": "test/one", "answer": "PRIVATE ONE"}, {"model": "test/two", "answer": "PRIVATE TWO"}],
            "comparison": {"answer": "MERGED OPINION"},
        },
    )
    history = json.dumps(storage.research_history(session_id, "test/one"))
    assert "PRIVATE ONE" in history
    assert "PRIVATE TWO" not in history
    assert "MERGED OPINION" not in history
    interrupted, _ = storage.create_run(request)
    storage.init()
    assert storage.get_run(interrupted)["status"] == "interrupted"
    assert storage.events(interrupted)[-1]["payload"]["type"] == "interrupted"
