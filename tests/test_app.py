import json
import time

import pytest
from fastapi.testclient import TestClient

from parallax import config, storage
from parallax.app import app
from parallax.schemas import RunRequest


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


def test_one_model_is_allowed_and_bounds_remain_enforced(client):
    response = client.post("/api/runs", json=body(models=["test/one"]))
    assert response.status_code == 201
    saved = wait_done(client, response.json()["run_id"])
    assert len(saved["result"]["reports"]) == 1
    assert not saved["result"]["comparison"]["agreements"]
    assert client.post("/api/runs", json=body(models=[])).status_code == 422
    assert client.post("/api/runs", json=body(models=[f"test/{i}" for i in range(5)])).status_code == 422


def test_catalog_includes_chinese_tool_models_with_metadata(client, monkeypatch):
    import httpx

    from parallax import app as app_module

    real_client = httpx.AsyncClient
    entries = [
        {
            "id": "qwen/example",
            "name": "Qwen: Example",
            "supported_parameters": ["tools"],
            "context_length": 128000,
            "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        },
        {"id": "deepseek/example", "name": "DeepSeek", "supported_parameters": ["tools"]},
        {"id": "other/no-tools", "name": "Other", "supported_parameters": []},
        {"id": "other/image", "supported_parameters": ["tools"], "architecture": {"output_modalities": ["image"]}},
        {"id": "bad"},
    ]

    def transport(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/models"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"data": entries})

    monkeypatch.setattr(app_module.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw))
    models = client.get("/api/models").json()["models"]
    assert [m["id"] for m in models] == ["qwen/example", "deepseek/example"]
    assert models[0]["context_length"] == 128000
    assert models[0]["pricing"]["prompt"] == "0.000001"


def test_catalog_failure_preserves_configured_choices(client, monkeypatch):
    import httpx

    from parallax import app as app_module

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        app_module.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(503)), **kw)
    )
    result = client.get("/api/models").json()
    assert result["models"] == config.DEFAULT_MODELS
    assert result["warning"]
