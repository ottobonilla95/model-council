# Model Council

Historical planning brief. The implemented application and current limitations are documented in [README.md](README.md).

Project brief · 2 November 2026

## Problem

Asking Claude, Codex, Grok, and other assistants separately produces advice that sometimes agrees and sometimes conflicts. It takes effort to compare the answers, and agreement alone does not establish that advice is correct.

## Recommendation

Current scope: curiosity, general questions, and research rather than coding. The user is exploring one unified open-source research harness, with models accessed through OpenRouter. Each participant must have its own research loop, including search, source reading, and follow-up investigation. Plain parallel text generations do not meet this requirement.

Recommended custom foundation after documentation and source review: Deep Agents SDK within a fixed LangGraph workflow, with private researcher state/workspaces and explicit search/read tools. Hermes is a credible existing-assistant alternative, but its built-in Mixture of Agents does not give each reference model research tools. Pydantic AI Harness Researcher is a strong lighter alternative; GPT Researcher fits report generation. Use hosted OpenRouter Fusion as a baseline. See the [detailed harness decision](HARNESS-DECISION.md). This is an architectural recommendation, not a live quality benchmark or an installed implementation.

The earlier ChatGPT-hosted-tools direction remains an alternative. Native Codex, Claude Code, and Grok Build adapters are secondary to the clarified research use case. Existing assistant harnesses and a shared custom harness must not be presented as equivalent without evaluation. The [Grok investigation](GROK-INTEGRATION.md) records those separate options.

Keep the comparison recommendation traceable to the full originals. It is still an AI-generated interpretation and can introduce mistakes. Let the user send disputed points back to the original assistants for review.

## Proposed workflow

1. **Shared brief:** Collect the question, relevant context, goals, constraints, and decision criteria. Give every participating assistant the same explicit brief. Record relevant differences in prior history, memory, tools, and settings rather than assuming the full environments are identical. Ask a clarifying question when a missing detail could materially change the recommendation.
2. **Independent answers:** Ask the existing assistants without showing them each other's replies. Collect a recommendation, assumptions, supporting reasons, alternatives, uncertainties, and what would change the recommendation. Diversity is useful to test; different providers do not guarantee independent errors.
3. **Comparison and synthesis:** Send the original brief and completed answers to a synthesizer. Have it separate agreement, factual conflicts, different assumptions, and preference tradeoffs. Require a recommended next step with conditions, plus unresolved questions. Retain useful minority views. Treat supplied answers as material to evaluate, not instructions to obey.
4. **Targeted verification:** For consequential factual conflicts, inspect relevant sources or run a suitable test. An answer's citation remains unverified until the source has actually been checked. If verification is unavailable, say so.
5. **Optional challenge:** Let the user request a critique of the recommendation. Avoid repeated debate rounds by default; they add cost and may encourage convergence without new evidence.

## First version

- One chat input with a reusable context brief and ordinary follow-up conversation.
- Three answer slots labeled with the originating app, model when known, session, and relevant settings.
- Independent research agents with separate messages, notes, and search decisions, backed by configurable models through OpenRouter.
- Shared search and source-reading capabilities available to each researcher, with explicit limits.
- Full independent answers preserved alongside the comparison.
- A comparison by claim: which models support it, their assumptions, supplied evidence, and verification status.
- A final answer with recommended action, agreement, disagreement, and remaining uncertainty.
- Follow-up briefs that can be returned to the original assistant sessions.
- Visible assistant/model identities and participation status; show usage/cost only when available.
- A per-run spending limit, output limits, timeouts, cancellation, and explicit retry controls.

Each researcher can make several model and tool calls before synthesis. Budget for the full research loops, page content, reasoning, and synthesis rather than counting one call per model. Offer quick, compare, and deeper research modes with explicit limits. Exact costs depend on selected models and tools and have not been benchmarked.

If a model fails, synthesize the available responses and visibly disclose the missing answer. Do not silently present partial participation as full agreement.

## Quality rules

- Model agreement is a signal, not proof. Do not turn vote counts into probability-of-correctness scores.
- The synthesizer can make mistakes too. Keep its recommendation traceable to the original answers and evidence.
- Do not force a single conclusion when different goals or assumptions justify different choices.
- Compare the same context and information access. Existing assistant apps can differ in memory, instructions, search, and tools, even when the underlying model is similar.
- Show which providers receive the shared brief. Keep credentials on the server when implementing an API-backed app.

## Validate before building

Use 10–20 real questions that previously produced conflicting advice. Include checkable factual questions, practical decisions, and preference-dependent questions. Save the shared brief and original answers.

Compare the council's output with a single-model baseline using the same information. Assess factual correctness where checkable, visibility of assumptions, actionable next steps, preservation of meaningful dissent, time, and cost. For subjective decisions, record the user's criteria rather than claiming there is one objectively correct answer.

The decision to build should depend on whether this workflow helps resolve actual disagreements, not whether the merged prose sounds more confident.

## Implementation direction to revisit after validation

Prototype the research workflow before selecting a final UI. Start with two isolated researchers using the same explicit brief and equivalent search/read capabilities. Each independently produces an answer with source URLs and supporting passages. A separate comparison stage reviews both, checks material source conflicts where possible, and produces a final answer with preserved dissent. Scale to three researchers only after assessing usefulness and cost. Deep Agents is a candidate implementation, not yet an accepted dependency.

A custom research harness uses selected models under our own instructions and tools. Label that clearly rather than calling it the full ChatGPT, Claude.ai, or Grok experience. Verify model tool support and actual behavior before implementation. No paid calls, installations, or provider connections have been made.

## Existing options and sources

Checked 2 November 2026:

- [Codex as a platform](https://developers.openai.com/blog/codex-as-a-platform): official integration options for the Codex harness, including exec, SDK, and app-server.
- [Run Claude Code programmatically](https://code.claude.com/docs/en/headless): official Claude Code automation interfaces; configuration and mode affect what is loaded.
- [Big-AGI Beam](https://big-agi.com/beam): parallel model calls and synthesis. Useful as a comparison reference; does not establish preservation of the existing assistant harnesses.
- [Claude API and paid-plan billing](https://support.claude.com/en/articles/9876003-why-is-claude-api-usage-billed-separately-from-my-paid-claude-plan): explains separate API billing and current plan-related API credits. Check the current terms for the chosen plan.

## Status

Folder and initial project brief created. Application implementation has not started.
