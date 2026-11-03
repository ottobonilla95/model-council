# Research harness decision

Investigated 2 November 2026. Scope: a conversational assistant for curiosity, advice and research, with multiple models investigating independently before comparison. This is a documentation and source-code review, not a live accuracy benchmark. No frameworks were installed or paid model calls made.

## Recommendation

**For a custom Parallax app, use the Deep Agents SDK inside a fixed LangGraph workflow.** OpenRouter supplies models; a shared search/read integration supplies research tools. Each selected researcher has its own state and evidence workspace. The workflow launches all of them, saves their answers, and then runs comparison and targeted verification.

This is my assessment of architectural fit, not proof that Deep Agents gives more accurate answers. Hermes remains a strong existing-assistant option. My earlier “try Hermes first” advice did not clearly distinguish adopting a personal assistant from building this controlled research panel. Pydantic AI Harness Researcher is a serious lighter alternative, and OpenRouter Fusion is the closest hosted baseline.

## Requirements that decide the choice

1. Each selected model can repeatedly search, read sources and investigate follow-ups.
2. Researchers receive the same explicit user context, without sibling answers.
3. The application guarantees participation by the selected models.
4. Original answers, sources and failures survive synthesis.
5. Chat history preserves user preferences without silently feeding previous merged conclusions into a new independent round.
6. The application can limit usage and runtime, cancel work and identify actual models used.

## Candidate comparison

| Candidate | What exists | What remains for this project | Assessment |
| --- | --- | --- | --- |
| Deep Agents + LangGraph | Agent loop, context management, model/tool configuration, subagents, workflow and persistence integration | Search/read tools, enforced isolation, fixed research stages and UI | Recommended custom foundation |
| Hermes Agent | Existing assistant surfaces, web tools, memory and delegation | Guaranteed model participation, routing or separate runs, durable evidence comparison | Prefer when adopting its assistant interface |
| Pydantic AI Harness Researcher | Composed research stack, typed results, configurable agents and delegation | Research workflow, persistence and product interface | Strong lighter alternative |
| GPT Researcher | Research planning, retrieval, source collection and report generation | Independent per-model runs and conversational comparison | Prefer for reports |
| Mastra | Agents, workflows, memory, streaming and research panel patterns | Research configuration and comparison application | Credible TypeScript option |
| smolagents | Small framework with multi-agent web examples | More application lifecycle and comparison work | Viable; no decisive advantage found here |
| OpenRouter Fusion | Hosted parallel panel, research tools and structured comparison | UI, evaluation and controls beyond its API | Closest hosted baseline; not an OSS harness |

## Deep Agents: useful foundation, not a finished research app

The SDK reuses agent/context machinery and integrates with configurable models and tools. Its research guide adds search and page fetching. OpenRouter has an official LangChain integration with tool calling. LangGraph supplies predetermined workflow paths and persistence. Self-hosting the SDK does not require selecting the managed service.

Sources: [research guide](https://docs.langchain.com/oss/python/deepagents/deep-research), [OpenRouter integration](https://docs.langchain.com/oss/python/integrations/chat/openrouter), [workflows](https://docs.langchain.com/oss/python/langgraph/workflows-agents), [persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

Source inspection revealed an important isolation detail: ordinary subagents get a fresh task message but inherit eligible state. The default general-purpose child uses the parent's backend; forked children deliberately inherit conversation history. Fresh chat context therefore does not automatically mean private evidence storage.

Sources: [subagent state preparation](https://github.com/langchain-ai/deepagents/blob/1f9d08c33f2f4e8cb236897342f8f3d6d1840220/libs/deepagents/deepagents/middleware/subagents.py), [backend construction](https://github.com/langchain-ai/deepagents/blob/1f9d08c33f2f4e8cb236897342f8f3d6d1840220/libs/deepagents/deepagents/graph.py).

For this app, use separate researcher instances/state namespaces and private evidence workspaces. Start them directly from the outer workflow; do not rely on a supervisor deciding to call every model. Disable nested delegation initially. Preserve full answers and evidence before synthesis. Each researcher still uses the existing harness for its own research loop.

Search and reliable source extraction remain integrations we must supply. The example search/fetch code is a starting point, not a complete browser/PDF retrieval system. The comparison UI and claim verification are also application work.

## Hermes: two different multi-model mechanisms

**Built-in Mixture of Agents does not meet independent research requirements.** Reference models advise without tool schemas; the aggregator operates the tools. This gives multiple perspectives, but does not give every model its own web investigation. Source inspection corroborates the advisory reference path.

Sources: [MoA documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents), [reviewed implementation](https://github.com/NousResearch/hermes-agent/blob/18399981f2bfa6256f63322a6470c766ffe6c572/agent/moa_loop.py).

**Delegation does create children with tools.** Default batches use one configured delegation model. The official advanced-delegation plugin adds per-task model/profile routing. Separate Hermes sessions can also be driven through documented integration interfaces. Thus Hermes can support the proposed research panel, with explicit orchestration.

Hermes documents full delegation logs, but automatic seven-day pruning means the application should retain evidence it promises to keep. Workspace privacy and fixed participation still need enforcement.

Sources: [delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation), [official plugin entry](https://github.com/NousResearch/hermes-agent/blob/18399981f2bfa6256f63322a6470c766ffe6c572/plugin-catalog/advanced-delegation.yaml), [integration interfaces](https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration).

Why choose Deep Agents for the custom app? It exposes the agent/workflow building blocks directly. Hermes would mean adapting an existing assistant's session and delegation conventions. If we keep Hermes's assistant interface instead, its existing memory and tools may save substantial product work. This is a scope distinction, not a research-quality ranking.

## Pydantic AI Harness Researcher

The current Researcher capability packages search, fetching, delegated research and output-size management. OpenRouter is supported, custom children can use different models, and application code can control independent runs. The Harness uses 0.x versioning with potentially changing minor-release APIs.

Reviewed source confirms a compact composition of capabilities with local search/fetch enabled and configurable subagents. This could simplify a smaller implementation. There is no head-to-head accuracy evidence here to dismiss it or claim Deep Agents is superior.

Sources: [Researcher](https://pydantic.dev/docs/ai/harness/researcher/), [subagents](https://pydantic.dev/docs/ai/harness/subagents/), [OpenRouter](https://pydantic.dev/docs/ai/models/openrouter/), [implementation](https://github.com/pydantic/pydantic-ai/blob/6ea3f5f6be1eed58db4b196913f63fd3a2920cd1/src/pydantic_ai_harness/pydantic_ai_harness/researcher/_capability.py).

## Other candidates

GPT Researcher is closer to a report pipeline. A research panel would run separately configured researchers; specialist roles alone are not independent model opinions. Reviewed code creates per-instance configuration and source collections and copies mutable defaults. Prefer per-run configuration over changing process environment variables during concurrent jobs. Pin all relevant LLM roles before attributing a report to one model.

Sources: [configuration](https://docs.gptr.dev/docs/gpt-researcher/gptr/config), [provider support](https://docs.gptr.dev/docs/gpt-researcher/llms/supported-llms), [agent code](https://github.com/assafelovic/gpt-researcher/blob/3582a6841fe7dc801e2a34e34ee408641aea9bce/gpt_researcher/agent.py), [configuration code](https://github.com/assafelovic/gpt-researcher/blob/3582a6841fe7dc801e2a34e34ee408641aea9bce/gpt_researcher/config/config.py).

Mastra's documented research workflow patterns make it a credible TypeScript option. smolagents provides multi-agent web examples. Neither showed a decisive advantage for these requirements in this review; neither was quality-benchmarked.

Sources: [Mastra multi-agent guide](https://mastra.ai/docs/guides/multi-agent-systems), [Mastra agents](https://github.com/mastra-ai/mastra/blob/main/docs/src/content/en/docs/agents/overview.mdx), [smolagents example](https://huggingface.co/docs/smolagents/v1.22.0/en/examples/multiagents).

LangChain's older Open Deep Research repository is archived. Treat it as an architectural reference, not the default new dependency. [Repository](https://github.com/langchain-ai/open_deep_research).

Fusion's beta API closely matches the idea: configurable parallel panel, search/fetch for each participant, analyst, raw answers and structured comparison. Its inner research is bounded: four tool-calling steps by default, configurable up to sixteen. Inspect and disclose partial failures. Use it as a baseline, not an assumed quality winner. [Fusion documentation](https://openrouter.ai/docs/guides/features/server-tools/fusion).

## Concrete first experiment

Start with two independent researchers and a separate comparison stage. Expand after measuring usefulness. Select current tool-capable model IDs during implementation.

```text
Question + explicit user context
              |
     fixed application workflow
        /                  \
Researcher A           Researcher B
own model              own model
own search/read loop   own search/read loop
private notes          private notes
        \                  /
     preserved answers + evidence
              |
   comparison + targeted source checks
              |
 answer, disagreements, originals, sources
```

Use equivalent configured research tools initially, while allowing different search decisions. Automatic provider-native tool selection can vary by model and complicate comparisons. Save source URLs, retrieval times and supporting passages where obtainable. Distinguish factual conflicts from different assumptions and preference tradeoffs. An unsupported majority must not overrule a well-supported minority.

Evaluate 10–20 real questions that previously caused disagreement. Compare one researcher, the two-researcher workflow and Fusion where available. Assess factual support, source accessibility, useful dissent, follow-up continuity, failures, time and total usage. Judge recommendations against the user's criteria. Fluent merged prose is not evidence of improvement.

Share user-supplied preferences across researchers. Keep previous AI conclusions separately labeled, and allow fresh rounds without them. Retain each researcher's own thread for follow-ups. Offer ordinary single-agent chat and an explicit, more expensive compare/research mode.

## Evidence and limits

This review establishes documented features and specific implementation behaviors. It does not establish accuracy, latency, actual cost, compatibility with every model endpoint, or parity with consumer ChatGPT, Claude.ai or Grok. A small comparative prototype is the next useful way to resolve those uncertainties.

Reviewed snapshots:

- Deep Agents: `1f9d08c33f2f4e8cb236897342f8f3d6d1840220`.
- Hermes: `18399981f2bfa6256f63322a6470c766ffe6c572`.
- Pydantic AI: `6ea3f5f6be1eed58db4b196913f63fd3a2920cd1`.
- GPT Researcher: `3582a6841fe7dc801e2a34e34ee408641aea9bce`.

GitHub API reported all four unarchived. Reported repository licenses: MIT for Deep Agents, Hermes and Pydantic AI; Apache-2.0 for GPT Researcher. This does not cover individual dependencies or hosted-service terms.
