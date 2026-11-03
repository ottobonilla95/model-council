import asyncio
import json

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from parallax.engine import ParallaxEngine, clean_citations, safe_error
from parallax.schemas import RunRequest
from parallax.web import ResearchWeb, validate_url


class ScriptedModel(BaseChatModel):
    model_id: str
    _tools: list = PrivateAttr(default_factory=list)
    _seen: list = PrivateAttr(default_factory=list)
    _calls: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "scripted-research-test"

    def bind_tools(self, tools, **kwargs):
        self._tools = tools
        return self

    def _generate(self, messages, **kwargs):
        raise NotImplementedError

    async def _agenerate(self, messages, **kwargs):
        self._seen.append(messages)
        self._calls += 1
        await asyncio.sleep(0.005)
        names = [t.get("function", {}).get("name", t.get("name")) if isinstance(t, dict) else t.name for t in self._tools]
        assert "task" not in names
        assert "execute" not in names
        if "Comparison" in names:
            brief = json.loads(messages[-1].content)
            source = brief["reports"][0]["sources"][0]
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "comparison",
                        "name": "Comparison",
                        "args": {
                            "answer": f"A supported conclusion [Source]({source['url']}).",
                            "agreements": [
                                {"claim": "Common evidence", "detail": "The same claim has support.", "source_ids": [source["id"]]}
                            ],
                            "disagreements": [],
                            "next_steps": [],
                            "limitations": [],
                        },
                    }
                ],
            )
        elif self._calls == 1:
            message = AIMessage(
                content="", tool_calls=[{"id": "search", "name": "web_search", "args": {"query": f"independent query {self.model_id}"}}]
            )
        elif self._calls == 2:
            data = json.loads(messages[-1].content)
            message = AIMessage(content="", tool_calls=[{"id": "read", "name": "read_source", "args": {"url": data["results"][0]["url"]}}])
        else:
            message = AIMessage(content=f"PRIVATE FINDING FROM {self.model_id}")
        message.usage_metadata = {"input_tokens": 100, "output_tokens": 25, "total_tokens": 125}
        message.response_metadata = {"model_name": self.model_id}
        return ChatResult(generations=[ChatGeneration(message=message)])


class FakeWeb(ResearchWeb):
    async def search(self, query):
        await self.take("search", query)
        source = self.add_source(f"https://example.org/{self.prefix}", "Primary source", "A relevant excerpt")
        return json.dumps({"results": [source]})

    async def read(self, url, offset=0):
        await self.take("read", url)
        source = self.add_source(url, "Primary source", "Full source text supports a narrow claim.", read=True)
        return json.dumps({"source": source, "text": "Full source text supports a narrow claim."})


@pytest.mark.asyncio
async def test_real_deepagents_tool_loop_parallel_workflow_and_isolation():
    events, models = [], []

    async def emit(event):
        events.append(event)

    def factory(model_id, key):
        model = ScriptedModel(model_id=model_id)
        models.append(model)
        return model

    request = RunRequest(
        mode="research", question="Compare the evidence", context="A shared constraint", models=["test/one", "test/two"], judge="test/judge"
    )
    engine = ParallaxEngine(
        request,
        "test",
        emit,
        {"openrouter": "fake", "tavily": "fake"},
        histories={"test/one": [{"role": "assistant", "content": "OWN PAST NOTE"}]},
        factory=factory,
        web_factory=FakeWeb,
    )
    result = await engine.run()
    assert len(result["reports"]) == 2
    assert all(r["status"] == "completed" for r in result["reports"])
    assert all(r["sources"][0]["read"] for r in result["reports"])
    assert all(r["tool_calls"] == 2 for r in result["reports"])
    assert all(r["usage"]["model_calls"] == 3 for r in result["reports"])
    assert result["comparison"]["agreements"][0]["source_ids"] == ["r1-s1"]
    types = [e["type"] for e in events if e["type"] != "route"]
    assert types[:2] == ["researcher_start", "researcher_start"]
    assert max(i for i, t in enumerate(types) if t == "researcher_done") < types.index("comparison_start")
    for model in models[:2]:
        prompts = str(model._seen)
        other = "test/two" if model.model_id == "test/one" else "test/one"
        assert f"PRIVATE FINDING FROM {other}" not in prompts
        assert ("OWN PAST NOTE" in prompts) == (model.model_id == "test/one")
    assert "PRIVATE FINDING FROM test/one" in str(models[2]._seen)
    assert "PRIVATE FINDING FROM test/two" in str(models[2]._seen)


@pytest.mark.asyncio
async def test_one_failed_model_does_not_prevent_comparison():
    async def emit(event):
        pass

    def factory(model_id, key):
        if model_id == "test/broken":
            raise RuntimeError("Provider unavailable")
        return ScriptedModel(model_id=model_id)

    request = RunRequest(mode="research", question="A question", models=["test/working", "test/broken"], judge="test/judge")
    result = await ParallaxEngine(
        request, "test", emit, {"openrouter": "fake", "tavily": "fake"}, factory=factory, web_factory=FakeWeb
    ).run()
    assert result["reports"][1]["status"] == "failed"
    assert any("test/broken" in x for x in result["comparison"]["limitations"])
    assert result["comparison"]["answer"].startswith("A supported conclusion")


def test_generated_unknown_citations_are_flagged():
    data = {
        "answer": "[Invented](https://made-up.example/fact)",
        "agreements": [{"claim": "x", "detail": "y", "source_ids": ["fake"]}],
        "disagreements": [],
        "limitations": [],
    }
    result = clean_citations(data, [])
    assert "https://made-up" not in result["answer"]
    assert result["agreements"][0]["source_ids"] == []
    assert result["limitations"]


def test_provider_errors_redact_credentials_before_exposing_them():
    message = safe_error(RuntimeError("Rejected key secret-provider-token"), {"openrouter": "secret-provider-token", "tavily": ""})
    assert "secret-provider-token" not in message
    assert "[redacted]" in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://127.0.0.1/private", "http://[::1]/", "http://user:pass@example.org/", "https://example.org:8322/"]
)
async def test_source_reader_rejects_private_or_unsupported_urls(url):
    with pytest.raises(ValueError):
        await validate_url(url)


class LoopingModel(ScriptedModel):
    async def _agenerate(self, messages, **kwargs):
        self._calls += 1
        message = AIMessage(
            content="", tool_calls=[{"id": f"loop-{self._calls}", "name": "web_search", "args": {"query": "keep searching"}}]
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.mark.asyncio
async def test_model_call_limit_stops_an_agent_that_keeps_searching():
    models = {}

    async def emit(event):
        pass

    def factory(model_id, key):
        model = LoopingModel(model_id=model_id) if model_id == "test/loop" else ScriptedModel(model_id=model_id)
        models[model_id] = model
        return model

    request = RunRequest(mode="research", question="A bounded question", models=["test/loop", "test/working"], judge="test/judge")
    result = await ParallaxEngine(
        request, "test", emit, {"openrouter": "fake", "tavily": "fake"}, factory=factory, web_factory=FakeWeb
    ).run()
    assert models["test/loop"]._calls == 6
    assert result["reports"][0]["status"] == "failed"
    assert "ModelCallLimitExceededError" in result["reports"][0]["error"]


@pytest.mark.asyncio
async def test_long_sources_are_read_in_continuable_chunks(monkeypatch):
    text = "First section. " * 1600 + "Final section with the counterargument. " * 600

    async def public(url):
        pass

    async def emit(event):
        pass

    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=text, headers={"content-type": "text/plain"}))
    original_client = httpx.AsyncClient
    monkeypatch.setattr("parallax.web.validate_url", public)
    monkeypatch.setattr("parallax.web.httpx.AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    web = ResearchWeb("fake", "r1", emit)
    first = json.loads(await web.read("https://example.org/long"))
    second = json.loads(await web.read("https://example.org/long", first["next_offset"]))
    assert first["text"] + second["text"] == text[:36000]
    assert first["source"]["read"] is True
    assert first["total_characters"] == len(text)


@pytest.mark.asyncio
async def test_web_action_limit_blocks_additional_searches():
    async def emit(event):
        pass

    web = FakeWeb("fake", "r1", emit, max_calls=1)
    await web.search("first")
    with pytest.raises(ValueError, match="limit reached"):
        await web.search("second")


class ScratchModel(ScriptedModel):
    async def _agenerate(self, messages, **kwargs):
        self._calls += 1
        if self._calls == 1:
            message = AIMessage(
                content="",
                tool_calls=[{"id": "write", "name": "write_file", "args": {"file_path": "/private.txt", "content": self.model_id}}],
            )
        elif self._calls == 2:
            message = AIMessage(content="", tool_calls=[{"id": "read", "name": "read_file", "args": {"file_path": "/private.txt"}}])
        else:
            message = AIMessage(content=f"My own scratch file contains: {messages[-1].content}")
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.mark.asyncio
async def test_same_scratch_filename_is_private_to_each_researcher():
    async def emit(event):
        pass

    request = RunRequest(mode="research", question="Keep private notes", models=["test/one", "test/two"], judge="test/judge")
    engine = ParallaxEngine(
        request,
        "test",
        emit,
        {"openrouter": "fake", "tavily": "fake"},
        factory=lambda model, _: ScratchModel(model_id=model),
        web_factory=FakeWeb,
    )
    results = await asyncio.gather(engine.research(0), engine.research(1))
    for index, result in enumerate(results):
        report = result["reports"][0]
        assert report["status"] == "partial"
        assert request.models[index] in report["answer"]
        assert request.models[1 - index] not in report["answer"]
