# Model Council

A local research chat that asks 2–4 models to investigate independently, then compares their answers with sources and meaningful disagreements intact.

Built with **Deep Agents, LangGraph, OpenRouter, FastAPI and a Vite interface**. This uses our own research harness around API models; it does not reproduce the consumer ChatGPT, Claude.ai or Grok applications.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Node.js 20.19+ or 22.12+. Python is managed by uv.

```sh
cd /Users/otto/Local/personal/model-council
./run.sh
```

Open [Model Council](http://127.0.0.1:8310). The launcher installs the locked Python dependencies and builds the frontend if no build exists. It binds only to this computer. To use another port, set `COUNCIL_PORT=8311`.

**Demo works without keys.** It runs the actual outer workflow with clearly labeled sample data, not generated answers. Arbitrary questions in Demo still receive the same illustrative findings.

For live research:

1. Open **Settings**.
2. Save an [OpenRouter key](https://openrouter.ai/settings/keys) and a [Tavily key](https://app.tavily.com).
3. Configure tool-capable model IDs and a comparison model in Settings. Select 2–4 researchers using the model buttons below the question box.
4. Switch **Demo mode** to **Live research** and ask your question.

Saving keys does not start a model call. “Key saved” indicates configuration, not a verified connection. Live research uses API credits; consumer chat subscriptions are separate. The app also refreshes OpenRouter's public model catalog when Settings opens.

Alternatively, copy `.env.example` to `.env` and set `OPENROUTER_API_KEY` and `TAVILY_API_KEY`. Locally saved Settings values take precedence over environment values. Credentials entered through Settings live in `data/credentials.json`, with owner-only file permissions. They are stored as plaintext locally and are never returned to the browser or included in research prompts. Do not expose this local app as a public server.

## What works

- Fixed LangGraph fan-out: every selected researcher starts before comparison.
- A separate Deep Agents instance and in-memory filesystem per researcher; no sibling answers, shared scratch files, host-file access or nested delegation.
- Each live researcher can repeatedly search Tavily and fetch public text pages, including further chunks of long pages.
- A separate comparison agent can check sources and returns the answer, agreement, disagreement, next steps and limitations.
- Original answers, source URLs/excerpts, retrieval times, activity, reported token usage and errors remain inspectable.
- Search snippets and pages actually fetched have different labels. Fetching is not presented as fact verification.
- Saved conversations, follow-up questions, shared context and a **Fresh round** option.
- Cancellation, partial failures, reconnectable event streams and JSON export.
- Configurable models through the current public OpenRouter catalog or manually entered IDs. No model substitution is intentionally requested.
- Responsive layout and keyboard navigation. Enter sends; Shift+Enter adds a line; Cmd/Ctrl+K opens a new conversation.

The main screen keeps the question box and model selection visible. **Options** holds shared context, research depth and Fresh round. Open conversation history from the top-left button; expand **Research activity** beneath a result for progress, limits and logs. Comparison, Originals and Sources remain available as result tabs.

Dark mode is the default. Use the sun/moon button in the header to switch themes; your preference is saved in this browser and applied before the app paints.

## Independence and history

Researchers get identical current questions and shared user context. Follow-ups include recent user questions and only that model's own prior final answers, capped to the last eight history messages and 18,000 characters per prior answer. They never receive sibling findings or the previous combined answer. **Fresh round** omits that history. Demo findings are excluded from live history.

The Deep Agents filesystem backend is new for each researcher and round. Scratch notes and the full internal agent state do not persist between rounds. SQLite preserves original final answers, collected source records, events and run settings. The comparison receives the reports only after all researchers finish or fail.

## Limits in this version

| Mode | Model calls per researcher | Web actions per researcher | Researcher timeout |
| --- | --- | --- | --- |
| Standard | 8 | 12 | 180 seconds |
| Deeper | 12 | 24 | 360 seconds |

The comparison gets up to 7 model calls in Standard, 10 in Deeper, 10 web actions and 240 seconds. Each model response is capped at 4,500 output tokens. At most two rounds run concurrently. These are work limits, **not a guaranteed dollar spending cap**; retries, reasoning, input tokens and provider pricing affect billing. Use provider-side credit limits as appropriate. Stopping cancels remaining work; provider requests already in flight may still be billed.

The reader supports text/HTML/JSON/XML over public HTTP(S), with a 2 MB response cap and 18,000-character chunks. PDFs, paywalls, image understanding, calculators, JavaScript-driven browsing and uploads are not implemented. Failed source access is visible to agents. Source records retain an excerpt, not an archival copy of the full page.

Citation cleanup checks generated Markdown links and source IDs against the collected source ledgers. It does not prove a cited source supports a claim. The comparison is still an AI interpretation. The system is instructed to preserve useful dissent and uncertainty rather than use majority vote as proof.

Completed answers survive a server restart; in-flight rounds become **interrupted**, not automatically resumed. There is no hosted deployment, login, encryption at rest or automatic cross-device sync. API failures and missing credits remain visible. End-to-end paid provider behavior and answer quality still need live evaluation with your keys.

## Develop and verify

```sh
uv sync --locked
uv run pytest -q
uv run ruff check council tests
cd frontend
npm ci
npm run build
```

For frontend development, run `uv run uvicorn council.app:app --host 127.0.0.1 --port 8310` in one terminal and `npm run dev` in `frontend` in another. Vite proxies `/api` to the backend. Rebuild the frontend to update the normal local app.

Tests exercise the real Deep Agents loop with scripted models, parallel workflow ordering, researcher isolation, structured comparison, partial failures, work limits, source chunking, local-address rejection, history privacy, cancellation, persistence, export, event replay and credential handling. They make no paid calls.

## Project files

- `council/engine.py`: Deep Agents researchers and the fixed LangGraph council.
- `council/web.py`: bounded search, public source reading and source ledgers.
- `council/storage.py`: local SQLite conversations, rounds and events.
- `council/app.py`: local API, event streaming and frontend serving.
- `frontend/src/`: interface and styles.
- `tests/`: behavioral checks using the real harness with deterministic model doubles.
- `data/`: private runtime data, excluded from Git. Set `COUNCIL_DATA_DIR` to change its location.

The original [project brief](PROJECT-BRIEF.md), [harness investigation](HARNESS-DECISION.md) and [Grok integration research](GROK-INTEGRATION.md) are retained. Architecture research was completed on 2 November 2026; the working application was built on 3 November 2026.
