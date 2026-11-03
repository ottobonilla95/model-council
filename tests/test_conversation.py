import json
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain_core.messages import AIMessage

from parallax import config, storage
from parallax.engine import ParallaxEngine, execute_run
from parallax.schemas import RunRequest
from parallax.web import OpenRouterWeb


class ConversationModel:
    def __init__(self, reply):
        self.reply = reply
        self.messages = []
        self.tools = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages, **kwargs):
        self.messages = messages
        return self.reply


@pytest.mark.asyncio
async def test_greeting_calls_only_one_model_and_never_creates_researchers():
    events, calls = [], []
    model = ConversationModel(AIMessage(content="Hey! What’s on your mind?"))

    async def emit(event):
        events.append(event)

    def factory(model_id, key):
        calls.append(model_id)
        return model

    request = RunRequest(question="hey", models=["test/one", "test/two"], judge="test/judge")
    result = await ParallaxEngine(request, "run", emit, {"openrouter": "key", "tavily": ""}, factory=factory).run()
    assert calls == [request.chat_model]
    assert result["mode"] == "chat"
    assert result["answer"].startswith("Hey!")
    assert not result["reports"]
    assert not any(e["type"] == "researcher_start" for e in events)
    assert [t["function"]["name"] for t in model.tools] == ["research_question"]


@pytest.mark.asyncio
async def test_auto_research_routes_followup_with_context_then_starts_independent_panel(monkeypatch):
    events = []
    model = ConversationModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "research_question",
                    "id": "route",
                    "args": {"question": "Compare holiday destinations in Sweden for December 2026"},
                }
            ],
        )
    )

    async def emit(event):
        events.append(event)

    async def research(self, index):
        assert self.research_question == "Compare holiday destinations in Sweden for December 2026"
        return {"reports": [{"agent": f"r{index + 1}", "model": self.request.models[index], "answer": "independent"}]}

    async def compare(self, state):
        assert len(state["reports"]) == 3
        return {"comparison": {"answer": "One combined answer"}}

    monkeypatch.setattr(ParallaxEngine, "research", research)
    monkeypatch.setattr(ParallaxEngine, "compare", compare)
    request = RunRequest(question="what about Sweden?", models=["test/one", "test/two", "test/three"], judge="test/judge")
    engine = ParallaxEngine(request, "run", emit, {"openrouter": "key", "tavily": ""}, factory=lambda *_: model)
    engine.conversation_history = [{"role": "user", "content": "I want a holiday in December 2026."}]
    result = await engine.run()
    assert result["mode"] == "research"
    assert len(result["reports"]) == 3
    assert "December 2026" in str(model.messages)
    assert next(e for e in events if e["type"] == "route")["question"].startswith("Compare holiday")


@pytest.mark.asyncio
async def test_explicit_chat_does_not_offer_research_tool():
    model = ConversationModel(AIMessage(content="I can explain the concept."))

    async def emit(event):
        pass

    request = RunRequest(question="Explain entropy", mode="chat", models=["test/one", "test/two"], judge="test/judge")
    result = await ParallaxEngine(request, "run", emit, {"openrouter": "key", "tavily": ""}, factory=lambda *_: model).run()
    assert not model.tools
    assert result["mode"] == "chat"


@pytest.mark.asyncio
async def test_openrouter_search_uses_real_annotations_without_tavily(monkeypatch):
    events = []

    async def emit(event):
        events.append(event)

    def handle(request):
        body = json.loads(request.content)
        assert body["tools"][0]["type"] == "openrouter:web_search"
        assert body["tools"][0]["parameters"]["max_uses"] == 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Never trust links in generated prose",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url_citation": {
                                        "url": "https://visitsweden.com/",
                                        "title": "Visit Sweden",
                                        "content": "Official tourism information",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr("parallax.web.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    web = OpenRouterWeb("secret", "r1", emit)
    result = json.loads(await web.search("holiday destinations 2026"))
    assert result["results"][0]["url"] == "https://visitsweden.com/"
    assert result["results"][0]["read"] is False
    assert web.calls == 1
    assert events[-1]["type"] == "sources"


@pytest.mark.asyncio
async def test_search_without_annotations_is_not_promoted_to_evidence(monkeypatch):
    async def emit(event):
        pass

    original = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "Invented https://fake.example"}}]})
    )
    monkeypatch.setattr("parallax.web.httpx.AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(ValueError, match="no source citations"):
        await OpenRouterWeb("secret", "r1", emit).search("question")


@pytest.mark.asyncio
async def test_chat_persists_reloads_and_restores_followup_context(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    storage.init()
    monkeypatch.setattr("parallax.memory.extract", AsyncMock(return_value=[]))
    model = ConversationModel(AIMessage(content="Hello Otto, I’ll remember that."))
    monkeypatch.setattr("parallax.engine.respond", lambda *args: fake_reply(*args))

    async def fake_reply(request, history, factory, api_key, usage):
        if request.question == "What is my name?":
            assert "Otto" in str(history)
        return {"mode": "chat", "answer": "Hello Otto, I’ll remember that.", "model": request.chat_model}

    first = RunRequest(question="My name is Otto", models=["test/one", "test/two"], judge="test/judge")
    run_id, session_id = storage.create_run(first)
    await execute_run(first, run_id, {"openrouter": "key", "tavily": ""}, {})
    saved = storage.get_run(run_id)
    assert saved["status"] == "completed"
    assert saved["result"]["answer"] == model.reply.content
    second = first.model_copy(update={"question": "What is my name?", "session_id": session_id})
    next_id, _ = storage.create_run(second)
    await execute_run(second, next_id, {"openrouter": "key", "tavily": ""}, {})
    assert len(storage.conversation_history(session_id)) == 4


@pytest.mark.asyncio
async def test_retry_reuses_saved_chat_reply_without_paid_call():
    async def emit(event):
        pass

    def forbidden(*_):
        pytest.fail("Completed chat reply should not trigger another paid call")

    request = RunRequest(question="hey", models=["test/one", "test/two"], judge="test/judge")
    engine = ParallaxEngine(request, "run", emit, {"openrouter": "key", "tavily": ""}, factory=forbidden)
    engine.saved_reply = {"mode": "chat", "answer": "Hey!"}
    assert (await engine.run())["answer"] == "Hey!"


def test_provider_timeout_is_in_sdk_milliseconds():
    from parallax.engine import model_factory

    assert model_factory("google/gemini-3.8-flash", "test-key").request_timeout == 65_000
