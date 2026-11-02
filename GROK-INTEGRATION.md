# Grok integration investigation

Checked 2 November 2026. Documentation investigation and local CLI inspection only; no live model request or account connection was performed.

## Findings

### Grok Build: a native coding-agent integration

The official coding agent supports headless prompts, JSON/streaming output, and an Agent Client Protocol (ACP) connection through `grok agent stdio`. Sessions and model selection are exposed. This offers a route for a ChatGPT tool to consult the real Grok Build agent.

Grok Build is already installed at `/Users/otto/.grok/bin/grok`. Local version: `1.0.50 (c58f321264ba) [stable]`. Local help confirms single-prompt mode, structured output, model selection, session resume, and agent mode. Authentication, model access, and successful generation remain untested. Local help says `--session-id` creates a new session; use `--resume` to continue one. Prefer installed CLI behavior where documentation differs.

Source: [Grok Build scripting and ACP](https://docs.x.ai/build/cli/headless-scripting), [Grok Build overview](https://docs.x.ai/build/overview).

### Grok chat: tools connect outward from the existing app

Grok chat accepts custom MCP connectors. We could expose shared question/result tools to Grok and ChatGPT. The user would open Grok and ask it to fetch a pending question and submit its answer. This keeps generation inside the Grok chat product, but the connector is not a documented external command to start a chat turn automatically. I did not establish a supported remote-control interface for normal Grok chat.

Source: [Grok connectors](https://docs.x.ai/grok/connectors).

### Grok API: built-in provider tools

The API supports server-managed web search, X search, code execution, and citations. It is more capable than a plain text-only model call, but does not establish parity with the consumer chat product or access to its personal memory/history. This is an optional fallback if the user accepts that distinction.

Source: [API tools overview](https://docs.x.ai/developers/tools/overview).

### Grok Bot: native cloud agent with a webhook trigger

A routine can accept an authenticated HTTP POST containing a JSON task. Acceptance starts work asynchronously; it does not return the finished answer. A proposed bridge would use a job ID, then have the Bot submit its answer through our MCP tool. Bot supports adding MCP servers, so the pieces are documented, but the combined workflow needs testing.

Important: Grok Bot is separate from Grok chat, and its FAQ says it can choose first-party or third-party models without a user model picker. It therefore cannot be treated as a guaranteed independent Grok-model opinion. Plan eligibility is not verified for this account.

Sources: [Webhook routines](https://docs.x.ai/grok-bot/skills-routines-and-automations), [Bot MCP connections](https://docs.x.ai/grok-bot/computer-and-apps), [Bot FAQ](https://docs.x.ai/grok-bot/faq).

## Recommendation for Model Council

- For coding and project questions, try a Grok Build adapter alongside Codex and Claude Code.
- If preserving the usual Grok chat experience is essential, use the shared MCP question/result bridge with a user-started Grok turn. Keep manual answer import as a fallback.
- Keep Grok API and Grok Bot visibly separate options. Do not silently substitute either for Grok chat.

## Proposed bridge, not implemented

ChatGPT would start a council job with the shared brief and selected participants. A backend would invoke configured local agents and store full answers with their source identity and session. ChatGPT would retrieve status/results and compare them. A local runner must be reachable by the backend; a cloud ChatGPT tool cannot simply execute a laptop CLI on its own.

For Grok chat participation, add authenticated tools such as `get_pending_question` and `submit_answer` to the same service. For Bot participation, a webhook could wake the Bot and its MCP connection could return the result. Keep job credentials scoped, originals intact, and missing/failed responses visible.

The next implementation check is an end-to-end question through one selected route, confirming configuration, identity, permissions, answer collection, and actual usage. No account changes or installations were made in this investigation.
