# Streaming-First LLM Routing and Orchestration

## Executive Summary

For a production chat system whose primary objective is low time-to-first-token (TTFT), the most transferable pattern is not “make every pre-answer component faster.” It is to classify work by whether it is required to safely and correctly start generation, then split the request into a short synchronous admission path and an asynchronous enrichment path. Mature projects repeatedly expose the same design principles: fast deterministic or local routing before expensive LLM classification, explicit graph branches instead of hidden agent loops, concurrent independent work, streaming event protocols, and a hard distinction between pre-stream failures and mid-stream failures.

The practical target architecture is a **streaming-first response envelope**: perform only authentication, request-shape validation, cheap policy checks, route selection, and minimum prompt construction before opening the downstream stream; start a baseline model as early as possible; run retrieval, visual grounding, telemetry, and non-critical safety/enrichment concurrently or after the first token; and use explicit events to disclose citations, tool progress, and post-answer corrections. This is an architectural recommendation derived from the project patterns below rather than a feature claim about any single project.

The projects are complementary rather than interchangeable. LiteLLM and Portkey are gateway/reliability layers; Semantic Router, RouteLLM, and vLLM Semantic Router address model or intent selection; LangGraph, LlamaIndex Workflows, and Haystack provide graph/pipeline orchestration; NeMo Guardrails and Guardrails AI address streaming-aware validation; Envoy External Processing illustrates a protocol-level way to keep response-body transformations streamed.

## What to Compare

| Project | Primary problem | Decision mechanism | Streaming/latency lesson |
|---|---|---|---|
| LiteLLM | Provider abstraction, load balancing, retries, fallbacks, auto-routing | Rules, heuristics, semantic keywords/embeddings, LLM or custom classifier, adaptive routing | Stream through the unified interface, but decide provider/model before the stream; do not assume transparent recovery after a stream has begun |
| Semantic Router | Fast intent/tool/model decisions | Embedding similarity, hybrid layers, optional local encoders/LLMs | Avoid a second generative LLM call for routine routing; use thresholds and a default fall-through |
| RouteLLM | Quality-cost model selection | Learned routers trained/evaluated against preference data | Treat routing as a measured model-selection problem; keep a deterministic fallback and benchmark routing overhead |
| vLLM Semantic Router | Signal-driven model/reasoning selection across heterogeneous infrastructure | Embeddings plus classifiers/ML selectors and programmable signals | Put routing close to the serving boundary, cache representations, and separate TTFT optimization from decode optimization |
| LangGraph | Durable, stateful agent graphs with conditional edges and tools | Explicit graph/workflow orchestration; nodes may contain LLMs/tools | Stream graph events/tokens; ensure async propagation and pass runtime config into model calls |
| LlamaIndex Workflows | Branching/concurrent retrieval and agent workflows | Event-driven workflow orchestration and agent handoffs | Start the workflow in the background and stream events, including LLM deltas and progress events |
| Haystack | Explicit RAG pipelines, conditional routing, loops | Declarative conditions, components, pipelines, agents | Keep routing and retrieval as independently testable components; use branches and bounded loops |
| NeMo Guardrails | Programmable input/output safety and topic controls | Rule/flow orchestration plus rail models | Stream chunks as soon as possible or validate chunks concurrently; configure chunk/context sizes deliberately |
| Portkey Gateway / Envoy ext_proc | Provider gateway, retries/fallbacks, request/response transformation | Ordered targets, status-code policies, proxy filters | Configure response processing as streamed rather than buffered; recovery policy must distinguish before- and after-first-byte failures |

## Project Analyses

### LiteLLM

**Problem solved.** LiteLLM provides a unified OpenAI-style interface across many model providers and adds router functions for load balancing, retries, cooldowns, and provider/model fallbacks. Its current routing documentation also describes a combined auto-router for complexity, semantic, and adaptive routing.[^1][^2][^3]

**Decision mechanism.** The documented auto-routing options include heuristics, an LLM classifier, lexical/semantic keyword rules, or a custom classifier plugin. Semantic routing can embed the incoming request, compare it against configured utterances, select the global maximum above a threshold, and otherwise use a default model. This makes LiteLLM useful as a reference for a layered policy: deterministic metadata and health routing first, semantic or complexity routing second, and an LLM classifier only when its value exceeds its latency and cost.[^3][^4]

**TTFT and optional work.** The unified API supports streaming by passing `stream=True`, so the gateway can preserve downstream token delivery. Routing, retries, and provider selection occur before or at the start of the provider call; they are not a substitute for an application-level plan that prevents retrieval or enrichment from delaying that call. The most important limitation is failure timing: an open issue explicitly notes that configured fallbacks are not generally supported after a failure occurs mid-stream. Therefore, classify a failure as pre-first-byte (safe to retry/fallback) or post-first-byte (usually emit an error/termination event, not a second answer stream).[^5][^6]

**Optional work and borrowed patterns.** Use LiteLLM-like routing as a gateway concern: provider health, cooldowns, retries, budget limits, and a default model should not be mixed with application intent or retrieval state. Precompute route configuration and embeddings; keep a cheap default route; attach route decisions and attempt IDs to tracing; and enforce a per-request “routing budget” so a slow classifier cannot block the primary stream.

**Read first.** Start with the routing/load-balancing documentation, auto-routing documentation, and streaming/getting-started documentation. In the repository, inspect the router implementation and streaming handler together; the search index shows `router.py` and `streaming_handler.py` as the relevant areas for fallback and mid-stream behavior.[^6][^1][^3][^5]

### Semantic Router

**Problem solved.** Aurelio Labs’ Semantic Router is a decision layer for LLMs and agents that routes based on semantic vector space instead of waiting for a slow generative LLM to decide which tool or path to use.[^7][^8]

**Decision mechanism.** A route contains a name and representative utterances; an encoder creates vectors and a router selects the best semantic match. The project supports hosted and local encoders, hybrid routing, multimodal encoders, and vector-index integrations such as Pinecone and Qdrant. The route can return no match below a score threshold, allowing a normal default handler rather than forcing a hallucinated tool call.[^9][^10][^7]

**TTFT and optional work.** The key latency advantage is eliminating a second LLM generation for common routing decisions. A local encoder or FastEmbed-style path can make the decision locally, while pre-encoded route utterances avoid repeated setup. The threshold/fall-through behavior is especially valuable: retrieval, tool invocation, and visual processing become opt-in branches rather than mandatory pre-answer stages.

**Optional work and borrowed patterns.** Use semantic routing for high-confidence decisions such as “needs web search,” “needs calculator,” “needs image understanding,” or “ordinary conversation.” Make the route output a typed plan containing `route`, `confidence`, `required_context`, and `fallback`; never treat a low-confidence route as permission to invoke an expensive branch. Keep a deterministic lexical/policy guard before semantic routing and a default direct-answer path after it.

**Read first.** Read the README for the static-route model and the encoder/index documentation. Then inspect `semantic_router/route.py`, the encoder implementations, and the router layer; the source exposes route schemas and function-call-related utilities.[^11][^12][^13]

### RouteLLM

**Problem solved.** RouteLLM is a framework for serving and evaluating LLM routers, with the stated objective of saving cost without compromising quality. It is best understood as a research-to-production reference for selecting among a strong and weak model, rather than as a complete gateway or agent runtime.[^14]

**Decision mechanism.** The important distinction is learned routing: the router is evaluated as a model-selection policy against quality preferences or benchmark outcomes, not merely as a hand-written keyword table. This makes it appropriate for studying routing thresholds, quality floors, abstention, and offline evaluation, while Semantic Router is a simpler semantic decision layer.

**TTFT and optional work.** A learned router can still add latency if it requires a remote model call. The production lesson is to deploy the router as a small local model or cached feature lookup, and to measure router latency as part of end-to-end TTFT rather than reporting only downstream generation speed. A default model should remain available when routing confidence is low or the router is unavailable.

**Optional work and borrowed patterns.** Log `(query features, chosen model, latency, cost, quality signal, fallback)` for replay. Define a quality floor and route only when the expected benefit exceeds routing overhead. For an educational assistant, route by task difficulty, need for citations, multimodal requirement, and learner context—not just by topic—then evaluate whether the route improves answer quality under a fixed TTFT budget.

**Read first.** Begin with the repository README and serving/evaluation entry points. Focus on the router abstractions, benchmark data schema, and serving adapter; treat the project as a measurement and policy reference rather than assuming that its learned router is a drop-in low-latency classifier.[^14]

### vLLM Semantic Router

**Problem solved.** vLLM Semantic Router is a programmable routing layer for mixture-of-models systems across cloud, data-center, and edge infrastructure. Its stated design is signal-driven routing for efficiency, safety, and adaptability.[^15]

**Decision mechanism.** The project combines semantic representations with model-selection methods; its package documentation describes KNN, KMeans, and SVM selectors trained from query, model, quality, and latency features, with local embedding generation and caching. This is a more operationally ambitious version of semantic routing: the decision can incorporate learned performance and infrastructure signals rather than intent alone.[^16]

**TTFT and optional work.** Running the router near Envoy/vLLM and using local inference reduces network hops and avoids a remote classifier in the critical path. The project’s related serving architecture emphasizes separate prefill and decode instances so TTFT and inter-token latency can be tuned independently. That separation is not necessary for an application-level chat service, but it is a useful mental model: optimize admission, prompt preparation, and prefill separately from token decoding.[^17]

**Optional work and borrowed patterns.** Build a route feature vector from modality, estimated token length, policy risk, retrieval requirement, model health, queue depth, and historical quality. Cache embeddings and route decisions where privacy and correctness allow. Keep a “reasoning required” or “visual required” signal explicit instead of making every request pass through a large model.

**Read first.** Read the repository overview and the model-selection package documentation. Then inspect the Envoy integration, embedding cache, and selection/training packages; those areas reveal how a router can be placed at the serving boundary while preserving a fallback model.[^15][^16]

### LangGraph

**Problem solved.** LangGraph models agent applications as explicit graphs with state, conditional edges, persistence, tools, and streaming. Its deployment/API documentation exposes streaming endpoints, background runs, task queues, persistence, webhooks, and monitoring for agent applications.[^18]

**Decision mechanism.** The core mechanism is graph/workflow orchestration: a node performs work, state is updated, and edges determine the next node. LLM calls and tool calls can be nodes, but routing is represented explicitly rather than hidden inside one opaque agent prompt. This supports bounded loops, human approval, and separate paths for direct answer, retrieval, tool execution, or escalation.

**TTFT and optional work.** LangGraph supports multiple stream modes, including events and token-level model events. The crucial implementation detail is that asynchronous model calls must preserve streaming configuration; project discussions show that passing runtime configuration into the model call is necessary for token events to propagate in some graph wrappers. For a production system, expose an event stream from the graph and let the UI render `answer_delta`, `tool_status`, `citation`, and `error` events independently.[^19][^20][^21][^22]

**Optional work and borrowed patterns.** Use a fast “direct answer” branch and a separate retrieval/tool branch. If retrieval is required for correctness, start retrieval concurrently with the earliest safe generation path, or stream a short acknowledgement/provisional answer only when product policy permits. Avoid starting a tool loop merely because an LLM mentioned a tool; represent tool eligibility and confidence in graph state, and cap iterations and wall-clock time.

**Read first.** Read the streaming how-to and token-streaming examples. Then inspect the Pregel/graph execution loop, runnable configuration propagation, stream writer, and checkpointing code. The source-level topics matter more than a single agent tutorial because the latency behavior is determined by scheduling and event propagation.[^22][^19]

### LlamaIndex Workflows

**Problem solved.** LlamaIndex Workflows provide event-driven orchestration for complex, branching, and concurrent logic, including retrieval and multi-agent workflows. Its documentation presents `AgentWorkflow` as an orchestrator for one or more agents with handoffs and shared state.[^23][^24][^25]

**Decision mechanism.** The mechanism is typed events and workflow steps. A step consumes an event and emits another event; the resulting design can branch, run concurrent tasks, and carry state without forcing every decision through an LLM. Agent handoffs are a specialized orchestration pattern on top of the workflow runtime.

**TTFT and optional work.** The workflow can run in the background while the caller consumes `stream_events()`. The documentation shows ordinary progress events in early/late steps and an async LLM generator emitting response deltas from the generation step. This is directly applicable to a chat protocol: send an early `run_started` or `planning` event, stream model deltas when available, and continue emitting retrieval/tool progress without making the client wait for the final workflow result.[^23]

**Optional work and borrowed patterns.** Model retrieval, reranking, visual grounding, and tool execution as typed events with explicit timeouts. Use parallel steps for independent enrichment, then merge only the artifacts needed by a later answer or citation stage. Preserve the partial answer and workflow state if an optional branch fails; do not convert an optional retrieval timeout into a blank response unless the query’s policy says retrieval is mandatory.

**Read first.** Read the workflow streaming documentation and the basic/multi-agent `AgentWorkflow` examples. Then inspect the workflow event types, handler, context event stream, and async step scheduler.[^24][^25][^23]

### Haystack

**Problem solved.** Haystack provides explicit components and pipelines for retrieval, generation, routing, agents, and loops. Its documentation maps graph-like orchestration to pipelines or agents and describes chat generators with streaming, structured-output, and multimodal support.[^26]

**Decision mechanism.** `ConditionalRouter` evaluates configured conditions and publishes outputs to connected branches. This is rule/condition routing rather than semantic classification by default, which is valuable for predictable gates such as “documents sufficient,” “image present,” “tool result available,” or “continue loop.” Haystack also supports agentic behavior when adaptive tool selection is required.[^27][^28]

**TTFT and optional work.** Explicit pipeline connections make blocking boundaries visible. A direct generator branch can be connected independently from a retriever branch, while a conditional route can decide whether more retrieval is needed. The framework’s streaming generator components and clear component boundaries encourage an event-oriented implementation, but the application still must ensure that no required pipeline join waits on optional branches.

**Optional work and borrowed patterns.** Use conditional routers for deterministic policy and data sufficiency; reserve an agent for genuinely open-ended tool choice. Use bounded loops for self-correction and retrieval expansion: Haystack documents that loops rerun components when inputs are ready and must eventually stop. Treat each component as a contract with timeout, cancellation, and degradation behavior.[^29]

**Read first.** Start with the ConditionalRouter and pipeline-loop documentation. Then read the router implementation and pipeline scheduler, followed by generator/retriever streaming components.[^27][^29]

### NeMo Guardrails and Guardrails AI

**Problem solved.** NeMo Guardrails provides programmable input/output rails for safety, topic control, and conversational policy. Guardrails AI provides streaming validation for generated text and structured data, with validators that can process chunks as they arrive.[^30][^31]

**Decision mechanism.** NeMo combines declarative flows, rail configuration, and rail models; Guardrails AI uses validator pipelines and chunk strategies. Neither should be treated as a single universal classifier: use inexpensive deterministic checks for obvious violations and model-based rails for cases requiring semantic judgment.

**TTFT and optional work.** NeMo’s streaming configuration explicitly offers `stream_first`: when true, chunks are streamed before output rails are applied; when false, chunks are checked before being sent, increasing blocking risk but preventing blocked chunks from reaching the client. NeMo also supports parallel input/output rails for independent I/O-bound checks, while its documentation warns that rewriting rails impose sequencing constraints. Guardrails AI similarly accumulates a sentence-sized or configured chunk before validation and streams validation results as they become available.[^32][^33][^31][^34][^30]

**Optional work and borrowed patterns.** Separate hard preconditions from post-first-token monitoring. For high-risk requests, block generation until input safety passes. For ordinary low-risk chat, run non-critical output checks concurrently with streaming, buffer a small chunk, and define what happens if a later chunk fails: terminate, redact, replace, or append a correction event. Do not silently claim that a streamed answer was fully validated if only prefixes were checked.

**Read first.** Read NeMo’s streaming-output and parallel-rails configuration documentation, then inspect the output-rail streaming implementation and tests. For Guardrails AI, start with the streaming and structured-data streaming documentation.[^31][^35][^36][^37][^30]

### Portkey Gateway and Envoy External Processing

**Problem solved.** Portkey Gateway is an open-source gateway for multi-provider access, retries, fallbacks, and routing. Its documentation describes automatic retries with exponential backoff and prioritized fallback targets selected after configured status codes or timeouts.[^38][^39]

**Decision mechanism.** Portkey uses configuration-driven target lists and error policies. Envoy External Processing is a lower-level proxy mechanism: a bidirectional gRPC stream lets an external processor inspect or mutate request/response headers and bodies, with processing modes that can be buffered, streamed, or disabled.[^40][^41]

**TTFT and optional work.** The Envoy model makes the latency boundary explicit: request JSON rewriting may be buffered, while response-body rewriting for streaming LLM output should use streamed processing to avoid waiting for the full response. Portkey’s fallback design is appropriate before the first byte, but once a response has been partially delivered, switching providers would create duplicated or inconsistent output unless the protocol has a deliberate continuation mechanism.[^42][^40]

**Optional work and borrowed patterns.** Put authentication, tenant policy, quotas, provider normalization, and observability at the gateway. Configure no-op/skip modes for response phases that do not need inspection. For visual context, pass references or signed object handles through the gateway rather than forcing the gateway to synchronously download and transform every image. For enrichment, use streamed side-channel events or post-response jobs rather than buffering the main answer.

**Read first.** Read Portkey’s fallback/retry documentation and gateway repository. Then read Envoy’s External Processing filter protocol and streamed response-body configuration.[^39][^43][^38][^40][^42]

## Cross-Project Architecture Patterns

### 1. Define a hard critical path

A useful critical path is: authentication and tenant limits; request parsing; cheap abuse/policy gate; route selection; minimum prompt assembly; downstream model connection; first visible event. Retrieval, reranking, image OCR, visual embedding, tool discovery, analytics, and post-answer evaluation should be classified as either required, speculative, or optional. Every component must declare its category and a maximum blocking budget.

### 2. Use a two-lane execution plan

The **fast lane** selects a safe baseline response path and opens the model stream. The **enrichment lane** runs retrieval, visual grounding, tool preparation, citation search, and telemetry concurrently. The enrichment lane can feed a later continuation, tool call, answer revision, or citation event, but it should not block the fast lane unless the request is explicitly marked `requires_grounding=true`.

A practical request state might be:

```text
RequestState {
  intent: direct | retrieve | tool | vision | unsafe | unknown
  confidence: float
  required_context: set[str]
  safety: pending | allowed | blocked
  primary_stream: unopened | open | ended
  enrichment: pending | ready | failed | timed_out
  fallback: available | used | unavailable
}
```

The invariant should be: **after `primary_stream=open`, no component may replace the already-emitted answer with a different provider response**. Before the first byte, retries and fallbacks are safe; after the first byte, emit a structured termination/error event and preserve the partial transcript.

### 3. Prefer cheap routing cascades

Use a cascade rather than one universal classifier:

1. Deterministic checks: modality, explicit commands, tenant policy, tool allowlist, token budget, cache keys.
2. Local lexical or embedding router: high-confidence route selection with a threshold and default fall-through.
3. Small learned classifier: task difficulty, safety risk, or model tier when enough labeled data exists.
4. LLM classifier: only for ambiguous cases whose expected quality gain exceeds its TTFT cost.
5. Final model/tool decision: constrained by the route plan and policy, not free to bypass system boundaries.

This combines Semantic Router’s fast semantic decision layer, LiteLLM’s configurable classifier choices, and vLLM Semantic Router’s learned performance signals.[^3][^7][^16]

### 4. Stream a typed event protocol

Do not expose only a raw token stream. Use SSE, WebSocket, or HTTP streaming events such as:

```json
{"type":"status","phase":"routing","route":"direct","confidence":0.94}
{"type":"status","phase":"retrieval","state":"started"}
{"type":"answer_delta","text":"..."}
{"type":"tool_call","name":"search","state":"started"}
{"type":"citation","id":"doc-17","span":[120,188]}
{"type":"warning","code":"optional_context_timeout"}
{"type":"done","usage":{},"degraded":true}
```

LangGraph and LlamaIndex demonstrate event streams that carry more than final text, while NeMo demonstrates chunk-level safety events. The UI can display immediate answer text while separately rendering evidence and progress.[^19][^31][^23]

### 5. Make optional work cancellable and degradable

Every retriever, reranker, vision worker, and tool should have a deadline, cancellation token, maximum fan-out, and failure class. If a branch is optional, its timeout should produce a degradation event—not an exception that cancels the primary stream. If a branch is required for factuality or safety, mark it as a pre-stream gate and accept the TTFT cost explicitly.

### 6. Treat guardrails as a policy matrix

Use blocking input rails for hard disallowed content, streaming output rails for low-to-moderate risk monitoring, and post-generation review for analytics or training. `stream_first=true` reduces visible delay but may expose a chunk before a rail rejects it; `stream_first=false` provides stricter prevention at the cost of buffering. This trade-off should be selected per risk class, not globally.[^34][^30]

### 7. Optimize serving only after orchestration boundaries

Once application-level blocking is removed, serving-level strategies become useful. vLLM’s disaggregated prefill design separates prefill and decode so TTFT and inter-token latency can be tuned independently. The same conceptual separation applies in a cloud deployment: isolate request admission and prompt preparation from decode capacity, measure queueing and prefill separately, and avoid attributing all TTFT to the model.[^17]

## Recommended Production Blueprint

```text
Client
  |
  v
Streaming API / event encoder
  |
  +--> Auth, quota, request validation, cheap safety gate
  |
  +--> Fast route cascade ------------------------------+
  |                                                     |
  |                                                     v
  |                                             Baseline LLM stream
  |                                                     |
  |                                                     v
  |                                             answer_delta events
  |
  +--> Enrichment supervisor (async, cancellable)
          +--> retrieval / rerank
          +--> visual grounding
          +--> tool preflight
          +--> citations / telemetry
          +--> output monitoring
                         |
                         v
             merge only at explicit safe points:
             tool call, continuation, citation, correction, done
```

For direct questions, the baseline stream should start immediately after the route cascade. For retrieval-required questions, launch retrieval and begin the stream only if the model can safely produce a transparent “searching” event or a grounded answer is not required until context arrives. For visual questions, detect image presence and modality early, but defer expensive OCR/vision enrichment unless the route confidence and task require it.

A useful operational dashboard should report TTFT decomposed into request admission, policy, routing, prompt assembly, queue wait, prefill, and first-token transport. Also record the percentage of requests that used each route, enrichment timeout rate, first-token-before-grounding rate, pre-stream fallback rate, post-stream failure rate, and quality outcomes by degradation mode. These measurements turn architectural choices into testable hypotheses.

## Reading Order

1. **Streaming and event semantics:** LangGraph streaming, LlamaIndex workflow streaming, and NeMo streaming rails.[^30][^19][^23]
2. **Fast classification:** Semantic Router route/encoder code and LiteLLM auto-routing.[^11][^3]
3. **Reliability boundaries:** LiteLLM fallback/streaming behavior, Portkey fallback/retry policies, and Envoy streamed external processing.[^38][^40][^6]
4. **Explicit orchestration:** Haystack ConditionalRouter and pipeline loops, followed by LangGraph graph execution and LlamaIndex event handlers.[^29][^23][^27]
5. **Serving-level TTFT:** vLLM Semantic Router and vLLM disaggregated prefill documentation.[^16][^17]
6. **Learned routing evaluation:** RouteLLM serving/evaluation code and benchmark methodology.[^14]

## Limitations and Verification Notes

Open-source projects differ in maturity, deployment assumptions, and version cadence. Documentation often describes intended behavior while issue threads reveal edge cases, especially around mid-stream fallback and callback propagation; those should be tested against the exact versions deployed. Several projects support streaming but do not automatically make optional work non-blocking: the application’s graph joins, middleware buffering, proxy configuration, and client parser can still erase the benefit. The safest implementation strategy is therefore to inspect the exact execution loop and write integration tests that assert the first `answer_delta` timestamp under slow retrieval, slow safety checks, tool timeouts, provider errors, and mid-stream disconnects.[^21][^6]

---

## References

1. [Routing & Load Balancing - LiteLLM](https://docs.litellm.ai/docs/routing-load-balancing) - Learn how to load balance, route, and set fallbacks (provider failover) for your LLM requests

2. [Load Balancing - Router - LiteLLM](https://docs.litellm.ai/docs/routing) - LiteLLM Router for load balancing, routing, retries, cooldowns, and fallbacks (failover) across mult...

3. [[Beta] Auto Routing - LiteLLM](https://docs.litellm.ai/docs/proxy/auto_routing) - One router for complexity, semantic, and adaptive routing. Classify each request with heuristics, an...

4. [Semantic Auto Router (deprecated)](https://docs.litellm.ai/docs/proxy/auto_routing_semantic) - The semantic Auto Router is superseded by Auto Routing, which folds semantic keyword matching, compl...

5. [Getting Started - LiteLLM](https://docs.litellm.ai/docs/) - LiteLLM is an open-source library that gives you a single, unified interface to call 100+ LLMs (Open...

6. [[Bug]: gemini fallback not working · Issue #8632 · BerriAI/litellm](https://github.com/BerriAI/litellm/issues/8632) - What happened? I have set up fallback like this: router_settings: fallbacks: [{"gemini-2.0-flash-thi...

7. [aurelio-labs/semantic-router: Superfast AI decision making ...](https://github.com/aurelio-labs/semantic-router) - Semantic Router is a superfast decision-making layer for your LLMs and agents. Rather than waiting f...

8. [GitHub - aurelio-labs/semantic-router: Superfast AI decision making and intelligent processing of multi-modal data.](https://github.com/aurelio-labs/semantic-router/tree/main) - Superfast AI decision making and intelligent processing of multi-modal data. - aurelio-labs/semantic...

9. [https://github.com/aurelio-labs/semantic-router](https://awesome.ecosyste.ms/projects/github.com%2Faurelio-labs%2Fsemantic-router) - Superfast AI decision making and intelligent processing of multi-modal data.

10. [Semantic Router](https://www.aurelio.ai/semantic-router) - NLP, LLM, Vector Search - Consultancy and Development

11. [semantic-router/semantic_router/route.py at main · aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router/blob/main/semantic_router/route.py) - Superfast AI decision making and intelligent processing of multi-modal data. - aurelio-labs/semantic...

12. [semantic-router/README.md at main · aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router/blob/main/README.md) - Superfast AI decision making and intelligent processing of multi-modal data. - aurelio-labs/semantic...

13. [semantic-router/docs at main · aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router/tree/main/docs) - Superfast AI decision making and intelligent processing of multi-modal data. - aurelio-labs/semantic...

14. [lm-sys/RouteLLM: A framework for serving and evaluating ...](https://github.com/lm-sys/routellm) - A framework for serving and evaluating LLM routers - save LLM costs without compromising quality - l...

15. [vllm-project/semantic-router: A programmable Mixture-of- ...](https://github.com/vllm-project/semantic-router) - vLLM Semantic Router is a programmable routing layer for building Mixture-of-Models systems across h...

16. [modelselection package - github.com/vllm-project/semantic-router ...](https://pkg.go.dev/github.com/vllm-project/semantic-router/src/semantic-router/pkg/modelselection) - Package modelselection provides ML-based model selection algorithms for choosing the optimal model f...

17. [Disaggregated Prefilling (experimental)](https://docs.vllm.ai/en/latest/features/disagg_prefill/)

18. [langgraph.txt - GitHub](https://raw.githubusercontent.com/esakrissa/mcp-doc/main/docs/langgraph.txt)

19. [langgraph/docs/docs/cloud/how-tos/stream_events.md at main · langchain-ai/langgraph](https://github.com/langchain-ai/langgraph/blob/main/docs/docs/cloud/how-tos/stream_events.md) - Build resilient language agents as graphs. Contribute to langchain-ai/langgraph development by creat...

20. [Parallel Tool Calling and LLM Token Streaming Issue #45 - GitHub](https://github.com/langchain-ai/langgraph/issues/45) - When calling chain.astream_events the tokens are streamed correctly. Adding config solved the proble...

21. [How to stream token of agent response in agent supervisor? #137](https://github.com/langchain-ai/langgraph/issues/137) - langgraph is able to pass callbacks to the llm to handle its stream … tutorials suggest to use graph...

22. [langgraph/how-tos/streaming-tokens/ #533 - GitHub](https://github.com/langchain-ai/langgraph/discussions/533) - langgraph/how-tos/streaming-tokens/ Build language agents as graphs https://langchain-ai.github.io/l...

23. [Streaming events](https://docs.llamaindex.ai/en/logan-material_docs/understanding/workflows/stream/)

24. [Multi-Agent Research Workflow with AgentWorkflow¶](https://docs.llamaindex.ai/en/latest/examples/agent/agent_workflow_multi/)

25. [AgentWorkflow Basic Introduction¶](https://docs.llamaindex.ai/en/latest/examples/agent/agent_workflow_basic/)

26. [Migrating from LangGraph/LangChain to Haystack | Haystack ...](https://docs.haystack.deepset.ai/docs/2.30/migrating-from-langgraphlangchain-to-haystack) - Whether you're planning to migrate to Haystack or just comparing LangChain/LangGraph and Haystack to...

27. [ConditionalRouter | Haystack Documentation - Deepset AI](https://docs.haystack.deepset.ai/docs/3.0/conditionalrouter) - `ConditionalRouter` routes your data through different paths down the pipeline by evaluating the con...

28. [ConditionalRouter - Haystack Documentation - Deepset AI](https://docs.haystack.deepset.ai/docs/conditionalrouter) - `ConditionalRouter` routes your data through different paths down the pipeline by evaluating the con...

29. [Pipeline Loops](https://docs.haystack.deepset.ai/docs/pipeline-loops) - Understand how loops work in Haystack pipelines, how they terminate, and how to use them safely for ...

30. [Guardrails Configuration#](https://docs.nvidia.com/nemo/guardrails/0.16.0/user-guides/configuration-guide/guardrails-configuration.html)

31. [Streaming](https://guardrailsai.com/guardrails/docs/concepts/streaming)

32. [Guardrails Configuration](https://docs.nvidia.com/nemo/guardrails/v0.22.0/configure-guardrails/yaml-schema/guardrails-configuration) - To enable parallel execution, set parallel: True in the rails.input and rails.output sections in the...

33. [Rail Engine Support | NVIDIA NeMo Guardrails Library ...](https://docs.nvidia.com/nemo/guardrails/reference/rail-engine-support) - Per-rail support matrix showing which built-in guardrail flows run on the LLMRails and IORails engin...

34. [Running Inference with Guardrails | NVIDIA NeMo Platform](https://docs.nvidia.com/nemo-platform/documentation/guardrail-models/core-concepts/running-inference)

35. [Executing Input and Output Rails in Parallel#](https://docs.nvidia.com/nemo/microservices/26.3.1/guardrails/tutorials/parallel-rails.html)

36. [Streaming structured data](https://guardrailsai.com/guardrails/docs/concepts/streaming-structured-data)

37. [feat: implement parallel streaming output rails execution by Pouyanpi · Pull Request #1263 · NVIDIA/NeMo-Guardrails](https://github.com/NVIDIA/NeMo-Guardrails/pull/1263) - This PR implements streaming for parallel output rails execution Add _run_output_rails_in_parallel_s...

38. [llms-full.txt](https://portkey.ai/docs/llms-full.txt) - AI Gateway Connect to 250+ AI models using a single consistent API. Set up load balancers, automated...

39. [Portkey-AI/gateway: A blazing fast ...](https://github.com/portkey-ai/gateway) - Fallbacks: Fallback to another provider or model on failed requests using the LLM gateway. Automatic...

40. [Set up the LLM auth proxy - Docs by LangChain](https://docs.langchain.com/langsmith/llm-auth-proxy-self-hosted)

41. [External Processing Filter (proto) - Envoy proxy](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/ext_proc/v3/ext_proc.proto)

42. [External processing service (proto)](https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/ext_proc/v3/external_processor.proto)

43. [External Processing - Envoy Gateway](https://gateway.envoyproxy.io/docs/tasks/extensibility/ext-proc/) - This task provides instructions for configuring external processing. External processing calls an ex...

