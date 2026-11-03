# Parallax

[Source repository](https://github.com/ottobonilla95/parallax)

A conversational assistant that answers everyday messages directly and automatically brings in 1–4 independent researchers when a question needs current sources or multiple perspectives. One reply stays in the chat; sources, original answers and disagreements are expandable.

Built with **Deep Agents, LangGraph, OpenRouter, FastAPI and a Vite interface**. This uses our own research harness around API models; it does not reproduce the consumer ChatGPT, Claude.ai or Grok applications.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Node.js 20.19+ or 22.12+. Python is managed by uv.

```sh
cd /Users/otto/Local/personal/parallax
./run.sh
```

Open [Parallax](http://127.0.0.1:8310). The launcher installs the locked Python dependencies and builds the frontend if no build exists. It binds only to this computer. To use another port, set `PARALLAX_PORT=8311`.

To start chatting:

1. Open **Settings** and save an [OpenRouter key](https://openrouter.ai/settings/keys).
2. Send a message. **Auto** is the default: greetings and ordinary questions get a direct reply from the selected chat model. Questions needing current information go to the research team.
3. Use message options to choose **Chat** (no search), **Research** (always use the team), research depth or shared context. Use **Models** below the input to search the live OpenRouter catalog, filter by provider, and select 1–4 models. Click a badge to choose the everyday chat model; use its × to remove it. At least one remains selected. The picker includes tool-capable models from providers such as OpenAI, Anthropic, Google, Qwen, and DeepSeek. Choices are saved per account in this browser. A single researcher returns its answer directly; two or more use the comparison model configured under Settings → Connections & comparison.

OpenRouter also supplies web search through its [web search server tool](https://openrouter.ai/docs/guides/features/server-tools/web-search), so no additional search key is required. [Tavily](https://app.tavily.com) remains an optional alternative. Missing credentials produce an actionable error; the interface never silently switches to sample responses. Legacy Demo rounds remain labeled in saved history, and the internal demo API is retained for tests.

Saving keys does not start a model call. “Key saved” indicates configuration, not a verified connection. Live research uses API credits; consumer chat subscriptions are separate. The app also refreshes OpenRouter's public model catalog when Settings opens.

Alternatively, copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. `TAVILY_API_KEY` is optional. Locally saved Settings values take precedence over environment values. Credentials entered through Settings live in `data/credentials.json`, with owner-only file permissions. They are stored as plaintext locally and are never returned to the browser or included in research prompts. Do not expose this local app as a public server.

## What works

- A conversational model responds directly or calls a typed research handoff, using recent conversation history to resolve follow-ups. No research panel is started for ordinary chat.
- Fixed LangGraph fan-out for research: every selected researcher starts before comparison.
- A separate Deep Agents instance and in-memory filesystem per researcher; no sibling answers, shared scratch files, host-file access or nested delegation.
- Each researcher searches through OpenRouter (or Tavily when configured) and reads public text pages, including further chunks of long pages. The OpenRouter search helper returns source annotations, never promotes uncited generated links to evidence, and caps searches to one per helper request with at most five results.
- A separate comparison agent can check sources and returns the answer, agreement, disagreement, next steps and limitations.
- Original answers, source URLs/excerpts, retrieval times, activity, reported token usage and errors remain inspectable.
- Search snippets and pages actually fetched have different labels. Fetching is not presented as fact verification.
- Saved conversations, follow-up questions, shared context and a **Skip conversation history** option.
- Cancellation, partial failures, reconnectable event streams and JSON export.
- Configurable models through the current public OpenRouter catalog or manually entered IDs. No model substitution is intentionally requested.
- Responsive layout and keyboard navigation. Enter sends; Shift+Enter adds a line; Cmd/Ctrl+K opens a new conversation.

The main screen is a message thread and composer, with the chat model and Auto mode visible. During research, badges show each selected model by name and spin while that model is working. If a comparison runs, its model gets a **Comparing** badge. Research produces one conversational answer. **Research details** under that reply holds sources, original answers, disagreements and export. The conversation drawer preserves the full thread, rather than replacing prior messages with report tabs.

Dark mode is the default. Use the sun/moon button in the header to switch themes; your preference is saved in this browser and applied before the app paints.

## Independence and history

The chat model sees up to twelve recent conversational messages, including combined research replies, and can resolve a follow-up into a self-contained question. Researchers get the same resolved question and shared user context. Follow-ups include recent user questions and only that model's own prior final answers, capped to the last eight history messages and 18,000 characters per prior answer. They never receive sibling findings or the previous combined answer. **Skip conversation history** omits that history. Demo findings are excluded from live history.

The Deep Agents filesystem backend is new for each researcher and round. Scratch notes and the full internal agent state do not persist between rounds. SQLite locally, or Postgres on Vercel, preserves original final answers, collected source records, events and run settings. The comparison receives the reports only after all researchers finish or fail.

## Personal settings and memory

Open **Settings** or your avatar → **Personal settings** to set a preferred name, response instructions and time zone. These settings sync through your account. Model selection and provider connections are under **Manage models**; existing browser-only background context is separate.

Parallax uses a bounded **semantic profile**: up to 50 concise facts and preferences per account, persisted in SQLite locally or Postgres on Vercel. This is fact memory, not embedding-based semantic search. The small profile is included in chat, independent research and comparison context; models are instructed to use details only when relevant. No additional database, embedding API or credentials are needed. Existing short-term conversation history remains separate. We do not automatically summarize old chats or retain agent reasoning as episodic memory, and models cannot rewrite their own system instructions.

**Use saved memories** controls both recall and learning. **Learn from our chats** can be paused separately while keeping recall enabled. Both are initially enabled. The helper reads only each new user message and that account’s saved memories, never web pages or assistant answers. It extracts stable, explicitly stated details, skips sensitive information by instruction, requires verbatim supporting evidence, and filters common secret/identifier patterns. Extraction is probabilistic: review incorrect facts in settings. A small **Memory updated** link appears under the reply when details are saved.

The helper uses the selected chat model, makes at most one additional model call per nontrivial message, and has a 12-second timeout. It runs alongside the reply; a memory failure leaves the answer available and shows a brief notice. Helper usage is additional to research budgets and uses the instance’s API credits. Greetings skip the helper. Manual edits are protected from automatic replacement. Corrections can replace automatically learned facts rather than accumulating contradictory entries. Full memory stops accepting new entries without silently evicting existing facts.

You can add, edit, forget individual memories, or forget all. Turning memory off preserves the stored facts. Forgetting removes saved facts from future cross-chat context; original messages remain in their conversations and can still appear in the current chat’s history. Old messages are not rescanned. In-flight extraction is invalidated when settings/memories change, so a pending helper cannot restore a just-forgotten entry. Account namespaces, authenticated/CSRF-protected endpoints, run ownership, lease checks and per-run deduplication prevent cross-user writes and retry duplication. Administrators have no endpoint to inspect other users’ memories. The unauthenticated loopback workspace uses its own local memory namespace, separate from signed-in accounts.

## Limits in this version

| Mode | Model calls per researcher | Web actions per researcher | Researcher timeout |
| --- | --- | --- | --- |
| Standard | 6 | 6 | 180 seconds |
| Deeper | 12 | 24 | 360 seconds |

The chat/routing call has a 70-second budget. The comparison gets up to 7 model calls in Standard, 10 in Deeper, 10 web actions and 240 seconds. Each model response is capped at 4,500 output tokens. OpenRouter search adds a bounded helper model request (up to 1,800 output tokens) and search charges per search action; these helper calls are separate from the researcher model-call budget. At most two rounds run concurrently. These are work limits, **not a guaranteed dollar spending cap**; retries, reasoning, input tokens and provider pricing affect billing. Use provider-side credit limits as appropriate. Stopping cancels remaining work; provider requests already in flight may still be billed.

The reader supports text/HTML/JSON/XML over public HTTP(S), with a 2 MB response cap and 18,000-character chunks. PDFs, paywalls, image understanding, calculators, JavaScript-driven browsing and uploads are not implemented. Failed source access is visible to agents. Source records retain an excerpt, not an archival copy of the full page.

Citation cleanup checks generated Markdown links and source IDs against the collected source ledgers. It does not prove a cited source supports a claim. The comparison is still an AI interpretation. The system is instructed to preserve useful dissent and uncertainty rather than use majority vote as proof.

Locally, completed answers survive a restart and in-flight rounds become **interrupted**. On Vercel, research runs use a durable queue and Postgres. Worker retries reuse completed researcher reports; an in-flight provider request may be repeated after a crash and can incur additional charges. Full agent scratch state is not checkpointed. API failures and missing credits remain visible. Answer quality and routing still need ongoing evaluation; automated tests use deterministic doubles. Live smoke checks cover a real greeting and a three-model travel research question.

## Vercel deployment

The repository deploys as one FastAPI project, with the Vite assets built during deployment. No Next.js migration is required. `vercel.json` sets Frankfurt and an 800-second function limit (requires Pro); `pyproject.toml` declares the private Python queue subscriber. Vercel Queues is currently in beta.

1. Import `ottobonilla95/parallax` into the personal Vercel workspace, using the repository root and the FastAPI framework.
2. Connect a separate Neon Postgres database. Use separate database branches for Production and Preview so preview testing cannot change production conversations. The integration supplies `DATABASE_URL`.
3. Configure Google sign-in and an explicit owner email as described below. Keep Vercel Authentication on all deployments while setting up and verifying application auth. Only after verification, and with the owner’s approval, restrict Vercel Authentication to previews so production visitors can reach Google sign-in.
4. Configure `OPENROUTER_API_KEY` (and optionally `TAVILY_API_KEY`) in the project's environment variables. Hosted Settings shows connection status but cannot write credentials to a local file. Secrets are never sent in queue messages.
5. Deploy and verify a greeting, automatic research, event reconnection, saved history and cancellation. Only OpenRouter is required for live chat and research. The frontend never substitutes Demo answers for user messages.

The hosted API uses Postgres for concurrency limits, job leases, cancellation, events and results. New server instances do not interrupt active jobs. A worker keeps a renewable lease and can only write while it still owns the round. Queue delivery retries up to three times; completed runs are idempotent. Research has a 690-second overall worker timeout. Expired abandoned jobs are marked interrupted when the app is next accessed. The queue publishes only saved run IDs and handles work independently from the browser connection.

For custom domains, also add the exact hostname to `PARALLAX_ALLOWED_HOSTS` (comma separated). Vercel-generated domains are accepted automatically. Never put provider secrets in frontend build variables. Local SQLite history is not uploaded automatically.

## Develop and verify

```sh
uv sync --locked
uv run pytest -q
uv run ruff check parallax tests
cd frontend
npm ci
npm run build
```

For frontend development, run `uv run uvicorn parallax.app:app --host 127.0.0.1 --port 8310` in one terminal and `npm run dev` in `frontend` in another. Vite proxies `/api` to the backend. Rebuild the frontend to update the normal local app.

Tests exercise the real Deep Agents loop with scripted models, parallel workflow ordering, researcher isolation, structured comparison, partial failures, work limits, source chunking, local-address rejection, history privacy, cancellation, persistence, export, event replay and credential handling. They make no paid calls.

## Project files

- `parallax/auth.py` and `parallax/accounts.py`: Google OIDC, revocable login sessions, account roles and administration.
- `parallax/memory.py`: account preferences, semantic profile storage, evidenced learning and correction controls.
- `parallax/conversation.py`: conversational reply and typed research routing.
- `parallax/engine.py`: Deep Agents researchers and the fixed LangGraph workflow.
- `parallax/web.py`: bounded search, public source reading and source ledgers.
- `parallax/storage.py`: SQLite/Postgres conversations, rounds, events and worker leases.
- `parallax/app.py`: API, event streaming and frontend serving.
- `parallax/jobs.py`: private Vercel Queue subscriber and retry-safe hosted execution.
- `frontend/src/`: interface and styles.
- `tests/`: behavioral checks using the real harness with deterministic model doubles.
- `data/`: private runtime data, excluded from Git. Set `PARALLAX_DATA_DIR` to change its location.

The original [project brief](PROJECT-BRIEF.md), [harness investigation](HARNESS-DECISION.md) and [Grok integration research](GROK-INTEGRATION.md) are retained. Architecture research was completed on 2 November 2026; the working application was built on 3 November 2026.


## Accounts and Google sign-in

Hosted deployments require sign-in and fail closed if authentication is not configured. Google OIDC uses Authlib with state, nonce, PKCE and ID-token validation. App sessions use random HttpOnly, SameSite=Lax cookies (Secure on HTTPS); only token hashes are stored in Postgres. Mutations require a session-bound CSRF token. Logging out revokes the current session, and changing a user’s access revokes all their sessions. No Google access or refresh tokens are retained.

Create a dedicated Google Cloud project and a Web application OAuth client. Register the exact redirect URI `https://YOUR-PRODUCTION-DOMAIN/auth/google/callback`. Use only the `openid email profile` scopes. Publish the Google OAuth audience when ready to accept accounts beyond test users. Google may require additional verification depending on branding and scopes.

Set these **Production** environment variables in the Parallax Vercel project, then deploy:

- `GOOGLE_CLIENT_ID`: OAuth web client ID (Config).
- `GOOGLE_CLIENT_SECRET`: OAuth client secret (Secret).
- `APP_SESSION_SECRET`: securely generated random value of at least 32 characters (Secret).
- `APP_BASE_URL`: exact canonical HTTPS production origin, without a trailing slash (Config).
- `PARALLAX_OWNER_EMAIL`: owner’s Google email (Config); this account gets the admin role.
- `PARALLAX_ALLOW_SIGNUP=1`: create a normal user on first verified Google sign-in. Set `0` to allow only users created by an administrator.

Previews must use separate OAuth credentials/origins and an isolated database; do not copy production secrets or data into them. The canonical production origin is used for OAuth redirects, so use that domain when signing in. Local auth is optional: without Google configuration, the loopback-only app retains its local workspace. Set `PARALLAX_REQUIRE_AUTH=1` to require sign-in locally as well. For a local Google test, add the exact localhost callback URI to a separate test client and set the corresponding env vars.

The owner can choose **Your account → Manage users**, create accounts by Gmail/Google Workspace email, change user/admin roles, and disable accounts. A pre-created account links to its verified Google identity on first sign-in. No invitation email is sent. Users can only list, read, stream, export, append to, or stop their own conversations; administrators do not get a chat-reading endpoint for other users. Conversations created before account sign-in stay out of signed-in history. The first person to register does not become the owner.

Provider credentials remain server-managed and shared for this instance. Signed-in users consume the operator’s API credits. The existing global two-run concurrency limit remains in place; this version does not implement billing or individual spend quotas. The `/privacy` page describes account, conversation and provider processing.
