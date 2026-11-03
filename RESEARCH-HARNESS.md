# Unified research harness: options

Superseded by the deeper [harness decision and source review](HARNESS-DECISION.md). This file records the initial shortlist.

Investigated 2 November 2026. The intended use is curiosity, general advice, and research. This is architecture research, not an implemented app or a benchmark.

## Recommendation

Use an existing agent harness for tool execution, context management, and persistence, then add the comparison workflow. Give each researcher the same explicit question and user context, its own isolated state, and equivalent search/read tools. Let it choose queries and pursue follow-ups without seeing the other researchers' conclusions. Bring answers and evidence together only after the independent stage.

OpenRouter supplies model access; the harness supplies the research process. Search can be provided through OpenRouter's managed tools or through a shared external search service. Opening and reading sources is necessary in addition to finding snippets. Select tool-capable model endpoints, record the actual model/provider, and expose routing failures rather than silently counting a substitute as an independent participant.

## Candidates

### Deep Agents: proposed custom foundation

An MIT-licensed, model-agnostic agent harness with isolated subagents, context management, persistence, and configurable tools. LangChain provides an OpenRouter chat-model integration and a research tutorial that combines independent research contexts, search, page fetching, and cited synthesis. We would still implement the research orchestration and user experience.

Sources: [repository](https://github.com/langchain-ai/deepagents), [research guide](https://docs.langchain.com/oss/python/deepagents/deep-research), [OpenRouter integration](https://docs.langchain.com/oss/python/integrations/chat/openrouter).

### GPT Researcher: research-focused alternative

An Apache-2.0 open-source research application/library with search, document research, and cited reports. Its supported-model list includes OpenRouter. It is worth trying when report generation is the central need; a panel of separately configured researchers and the comparison stage would need explicit design and validation.

Sources: [documentation](https://docs.gptr.dev/), [provider support](https://docs.gptr.dev/docs/gpt-researcher/llms/supported-llms).

### OpenRouter Fusion: hosted baseline

The beta Fusion tool runs a configurable panel in parallel. Its documentation explicitly enables web search and web fetch for each panel member and for the analyst. It returns raw responses plus a structured comparison; the outer model produces the final answer. This is a close baseline for the requested workflow, though it is a hosted service rather than an open-source harness we own. Inner tool steps and model outputs have configurable caps.

Source: [Fusion documentation](https://openrouter.ai/docs/guides/features/server-tools/fusion).

### Open Deep Research: reference only

LangChain's older `open_deep_research` repository is archived. Use its design as a reference rather than selecting it as the default dependency for new work.

Source: [archived repository](https://github.com/langchain-ai/open_deep_research).

## First experiment

Use a small set of real questions with checkable factual elements and questions with legitimate tradeoffs. Compare one research agent against two independent agents plus synthesis. Record correctness where checkable, citation support, useful disagreements, duration, and total usage. Keep the question and user context consistent across runs.

Each research answer should include a short conclusion, key claims with sources/passages, assumptions, missing evidence, and what would change the conclusion. The comparison should preserve useful minority findings and inspect source conflicts rather than infer truth from agreement.

Start with search and source reading. Add PDF extraction, a calculator, or browser rendering only when a real task needs them. Keep user preferences/conversation memory separate from temporary evidence and from other researchers' work. Store sources with retrieval dates so later answers can distinguish fresh evidence from old notes.

For the first version, expose quick, compare, and deeper research modes. Set limits on research steps, output length, runtime, and concurrent work. Make source failures and incomplete participation visible. Do not claim parity with a consumer assistant or higher accuracy until the workflow has been evaluated.
