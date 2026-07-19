# AREQA Pipeline Processing Improvement Plan

> Implementation Plan: Faster Non-RAG Chat Runtime With Controlled Model Budgets

This plan improves AREQA chat response speed without removing the product pipeline the user wants to keep. The current code shows that `/api/v1/stream` enters `OrchestrationService.execute()` and then synchronously performs routing, turn intake, optional policy classification, optional RAG/Web work, prompt assembly with hot and long-term memory, main LLM streaming, synchronous suggestions, and post-turn durable job dispatch. Internal RAG is already disabled unless `ENABLE_INTERNAL_RAG=true`, and the user confirmed RAG is not part of the current product path. Therefore, this plan optimizes the non-RAG path first, preserves Web Search when policy requires it, preserves behavior analysis and suggestions in the foreground, and keeps learner-state updates, reflection, compaction, and long-term organization in durable background work.

The phase order is deliberate: first add measurement, then introduce a deterministic turn plan and model-call budget, then run baseline-versus-TurnPlan experiments, then parallelize only the foreground stages that the trace proves are material bottlenecks, and finally optimize suggestions and validate the end-to-end latency/cost contract. Phase 3 must not be treated as a speculative rewrite. It should be driven by Phase 1 and Phase 2 evidence: if trace data shows that policy classification, turn intake, hot-memory loading, Web Search, or prompt assembly dominate the critical path, parallelize those specific stages; if the trace shows that suggestions or the main provider stream dominate instead, preserve the orchestration shape and prioritize the later suggestion/provider gates. This avoids guessing where latency comes from and avoids over-agentification. The existing `ConversationRuntime`, `RunContext`, `ConversationRunState`, `SearchPolicy`, `MemoryPolicy`, `TutorAgent`, `ToolRegistry`, `ToolBudgetTracker`, and latency benchmark script should be reused rather than replaced.

## Experiment-First Execution Rule

The implementer must complete Phase 1 and Phase 2 before making Phase 3 parallelization changes. After Phase 2, run a controlled comparison with the same prompt set and environment:

```text
baseline runtime
TurnPlan disabled compatibility mode
TurnPlan enabled non-RAG general route
TurnPlan enabled explicit-memory route
TurnPlan enabled Web-required route, if Web credentials are available
```

The comparison must include TTFT, total completion latency, main-model-start latency, suggestion latency, foreground model-call count, memory-query count, Web/tool count, cache status, and safe fallback reason codes. Phase 3 work items must cite the measured bottlenecks they address. If Phase 1/2 data does not show a meaningful preflight bottleneck, Phase 3 should be narrowed to duplicate-read removal and task ownership hardening instead of broad concurrency changes.

## Current Code Findings

- `backend/main.py` defaults `ChatRequest.use_rag` to `False`; `init_rag_service()` only initializes local RAG when `ENABLE_INTERNAL_RAG=true`.
- `backend/services/orchestration_service.py` emits early metadata/status/action events, but still awaits `TurnIntakeService.process()` before low-information short-circuit and before prompt assembly.
- `TurnIntakeService.process()` performs interaction timestamp updates, memory ingestion, and roleplay-state updates in the foreground. Memory ingestion can enter `MemorySemanticAnalyzer` when semantic analysis is enabled and acknowledged.
- `classify_dialogue_policy()` starts as a foreground policy task for every non-empty message with a client, then waits up to 1.5 seconds before prompt assembly.
- `ConversationContextService.build_conversation_context()` loads hot memory and then may run `MemoryQueryTool.execute()` for substantive queries. `MemoryQueryTool` concurrently queries cold and working memory, and cold memory may perform model-assisted embedding/query work through `gum_integration`/`cold_memory`.
- `PostTurnService.suggestion_events()` synchronously calls `SuggestionService.generate_suggestions()` after the main answer and before terminal completion.
- `docs/tech_docs/experience/agent_system.md` warns against over-agentification, implicit state sharing, missing stop conditions, and tool overload. The direct implication for this optimization is: keep deterministic wrappers as authority, use agents only for bounded choices, and make every model/tool call visible, budgeted, timed, and fallback-safe.

## Model-Call Position

The goal is not to remove every model-powered component. Many components are legitimate system modules: behavior analysis, search routing, memory semantic matching, query rewrite, main answering, and suggestions each serve different product needs. The performance problem is that multiple model calls can become unconditional foreground work. This plan changes invocation policy, not product capability:

- Keep model components when their output affects the current turn.
- Run deterministic rules before model calls whenever correctness does not require a model.
- Gate optional model calls by a turn plan, route reason, timeout, and per-run budget.
- Cache repeatable model outputs such as route decisions, query rewrites, and suggestion seeds.
- Move model calls that update future state into durable background jobs.
- Never let an agent decide privacy, memory scope, terminal SSE behavior, or durable side effects.

This is controlled agentic architecture only in the narrow sense that some dynamic choices are delegated to bounded components such as `TutorAgent`. It is not a plan to turn the whole runtime into a multi-agent loop.

### Phase 1: Add Foreground Latency Trace And Model-Call Accounting

#### Problem

The current pipeline has visible latency symptoms but limited internal attribution. `scripts/performance/benchmark_chat_latency.py` can measure client-visible milestones and contains mock variants, but the server does not emit a consistent per-run internal trace for routing, turn intake, behavior analysis, memory snapshot, long-term memory query, prompt assembly, main model start, first token, suggestions, and terminal completion. Without this, later optimization can reduce one synthetic bottleneck while shifting cost elsewhere.

#### Assumptions

RAG is not part of the active optimization path unless `use_rag=True` is explicitly sent. Existing SSE compatibility must remain unchanged for clients. Internal trace logs must not include raw user text, prompts, memory contents, model output, credentials, or sensitive labels. If live production observability requirements differ from local tests, this phase must still produce privacy-safe structured logs and a local testable trace object.

#### Solution

Add a run-local `TurnLatencyTrace` service that records named milestones and counters. `OrchestrationService.execute()` will create one trace per run and record safe phase timings and model/tool counters. This phase does not change behavior or ordering. It only makes the existing critical path measurable and gives later phases a regression target.

#### Implementation

> Context: Add Google-style docstrings for every new public module, class, and function. Document why the trace excludes raw content, which phase names are stable contract values, and how the trace treats failed or skipped phases. Use inline comments only where a privacy or compatibility boundary is non-obvious. Critical structured logs must be documented with event names, correlation IDs, safe phase names, elapsed milliseconds, skip/fallback reasons, and aggregate counters.

Add a proposed `backend/services/turn_latency_trace.py` with `TurnLatencyTrace`, `PhaseTiming`, and `ModelCallCounter`. The trace should support `mark(name)`, `measure(name)` as an async context manager if useful, `increment_model_call(kind)`, `increment_tool_call(kind, cache_status)`, and `snapshot()`. Use monotonic time for durations and wall-clock only for existing run metadata.

Modify `backend/services/orchestration_service.py` inside `OrchestrationService.execute()` to instantiate the trace after `runtime.start_session()`. Record at least: `request_accepted`, `search_routing_started`, `search_routing_finished`, `turn_intake_started`, `turn_intake_finished`, `policy_classifier_started`, `policy_classifier_finished`, `rag_skipped_or_started`, `web_search_started`, `web_search_finished`, `prompt_assembly_started`, `prompt_assembly_finished`, `main_model_started`, `first_answer_delta`, `main_model_finished`, `suggestions_started`, `suggestions_finished`, `post_turn_queued`, and `terminal_sent`.

Modify `ConversationStreamService.stream()` to optionally accept a trace and mark first answer delta plus model start/finish. The default must remain optional so existing tests and direct callers do not break.

Modify `PostTurnService.suggestion_events()` to optionally accept the trace and increment the suggestion model counter if the suggestion service exposes a model call or if the phase must be counted at the orchestration level.

Extend `scripts/performance/benchmark_chat_latency.py` only if needed to recognize a future `event: metadata` trace summary in live mode. Do not expose internal trace details to end users in SSE during this phase unless explicitly feature-flagged.

#### Expected File Tree After Phase 1

Cumulative tree for this phase only:

```text
backend/
├── services/
│   ├── orchestration_service.py         [modified]
│   ├── conversation_stream_service.py   [modified]
│   ├── post_turn_service.py             [modified]
│   └── turn_latency_trace.py            [new]
scripts/
└── performance/
    └── benchmark_chat_latency.py        [modified if live trace parsing is needed]
tests/
└── backend/
    ├── test_turn_latency_trace.py       [new]
    ├── test_orchestration_service.py    [modified]
    └── test_chat_latency_benchmark.py   [modified if benchmark parsing changes]
```

#### Work List

1. [ ] Create `backend/services/turn_latency_trace.py`.
   - [ ] Add proposed `PhaseTiming`, `ModelCallCounter`, and `TurnLatencyTrace`.
   - [ ] Add `TurnLatencyTrace.mark()` and `TurnLatencyTrace.snapshot()` with stable safe phase names.
   - [ ] Add optional counters for `completion`, `embedding`, `semantic_memory`, `policy_classifier`, `query_rewrite`, `suggestions`, `web_search`, and `memory_query`.
2. [ ] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [ ] Instantiate `TurnLatencyTrace` after `self.runtime.start_session()`.
   - [ ] Mark each current foreground phase without changing ordering.
   - [ ] Emit one safe structured log `orchestration.turn_trace_completed` before terminal completion.
3. [ ] Modify `ConversationStreamService.stream()` in `backend/services/conversation_stream_service.py`.
   - [ ] Add optional `trace` parameter.
   - [ ] Mark provider request start, first answer delta, stream completion, and stream failure.
4. [ ] Modify `PostTurnService.suggestion_events()` in `backend/services/post_turn_service.py`.
   - [ ] Add optional `trace` parameter and record suggestion start/finish/failure.
5. [ ] Add `tests/backend/test_turn_latency_trace.py`.
   - [ ] Assert phase durations are monotonic and snapshots contain only safe metadata.
   - [ ] Assert model counters can be incremented without raw prompt data.
6. [ ] Extend `tests/backend/test_orchestration_service.py`.
   - [ ] Assert a normal non-RAG turn logs `orchestration.turn_trace_completed`.
   - [ ] Assert the log contains safe phase names and does not contain the raw user query.

#### Test Plan

Run focused backend tests around trace behavior and existing orchestration contracts. Mock the LLM stream, suggestion service, and memory store to avoid external calls. Use `caplog` to assert event names and safe fields, not formatted sentences. Existing greeting, accumulator, search-mode, attachment, and durable-job tests must still pass.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_latency_trace.py tests/backend/test_orchestration_service.py tests/backend/test_post_turn_service.py -q
PYTHONPATH=. pytest tests/backend/test_chat_latency_benchmark.py -q
```

#### Expected Output / Result

Every chat run produces one privacy-safe structured trace log with phase durations and aggregate model/tool counters. User-facing SSE output remains compatible. No new model calls are added.

#### Testing Script

##### Act 01: Trace A Non-RAG Turn

Run a mocked `/api/v1/stream` orchestration path with `use_rag=False`, `use_web_search=False`, one user message, mocked prompt assembly, mocked LLM accumulator, and mocked suggestions.

Pass condition: `orchestration.turn_trace_completed` is logged once with phase timings and without the raw user message.

##### Act 02: Trace First Answer Delta

Run `ConversationStreamService.stream()` with a mocked streaming response that yields one content delta.

Pass condition: the trace snapshot contains `first_answer_delta` after `main_model_started`.

##### Act 03: Preserve SSE Contract

Run the existing accumulator/suggestions orchestration test.

Pass condition: no `event: accumulator` reaches the client and terminal `data: [DONE]` is still emitted once.

#### Gate to Enter the Next Phase

The next phase must not start until these commands pass:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_latency_trace.py tests/backend/test_orchestration_service.py tests/backend/test_post_turn_service.py tests/backend/test_chat_latency_benchmark.py -q
```

Retain the test output and one sample safe trace log. If any assertion fails, fix the trace or restore compatibility before proceeding.

#### Phase Commit

Commit message:

```text
feat(backend): add chat turn latency tracing
```

Stage only:

```text
backend/services/turn_latency_trace.py
backend/services/orchestration_service.py
backend/services/conversation_stream_service.py
backend/services/post_turn_service.py
tests/backend/test_turn_latency_trace.py
tests/backend/test_orchestration_service.py
tests/backend/test_post_turn_service.py
tests/backend/test_chat_latency_benchmark.py
scripts/performance/benchmark_chat_latency.py
```

Only stage files that were actually changed. Before committing, inspect `git status --short` and preserve unrelated user changes. Use path-specific staging or hunk staging, never broad staging when unrelated changes exist. Run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): add chat turn latency tracing"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 2: Introduce A Deterministic Foreground Turn Plan And Model Budget

#### Problem

Model-powered components are currently invoked by local conditions rather than a single foreground plan. `classify_dialogue_policy()` is started for every non-empty client-backed turn. `ConversationContextService` permits long-term memory query for most substantive queries. Memory semantic analysis can run during foreground turn intake when enabled. Web query rewrite can add another model call before external search. Suggestions are synchronous after the answer. These components are useful, but without a shared budget they can accumulate into several foreground model calls for simple questions.

#### Assumptions

The user wants behavior analysis, short-term memory, necessary prompt construction, main answer generation, and suggestions to remain in the foreground. RAG should remain available when explicitly requested but is not optimized as the default path. Privacy and memory policy remain deterministic; no agent may expand memory scope. If product owners later decide that every substantive query must synchronously query cold memory, the budget must make that cost visible rather than silently disabling it.

#### Solution

Add a deterministic `TurnPlanService` that classifies the current turn into a small set of foreground execution requirements. The plan does not answer the user and does not replace `TutorAgent`; it decides which existing components are allowed to run synchronously. It should produce a `TurnPlan` with fields such as `requires_policy_classifier`, `requires_long_term_memory`, `requires_web_query_rewrite`, `requires_suggestions`, `memory_scope`, `behavior_analysis_level`, `max_foreground_model_calls`, and safe reason codes.

The plan should keep components, not delete them. For example, the policy classifier may run only for learning/coaching turns where its output affects `effective_max_tokens` or style. Long-term memory may run synchronously only for explicit recall or when the deterministic memory policy requires it; otherwise it can be omitted from the current prompt or scheduled for future-state enrichment in a later phase. Suggestions remain foreground, but this phase budgets them explicitly.

#### Implementation

> Context: Add Google-style docstrings for every new public module, class, and function. Document the boundary between deterministic planning and agent routing, the reason each model component is allowed or skipped, and the fallback behavior when the model budget is exhausted. Inline comments should explain only high-risk policy decisions, such as why memory scope cannot be expanded by model output. Structured logs must use safe reason codes and include `run_id`, `conversation_id`, `route`, budget allowance, budget usage, and skip/fallback reasons without raw text.

Create `backend/services/turn_plan_service.py` with proposed dataclasses/enums:

- `TurnRoute`: `STATIC_GREETING`, `GENERAL_CHAT`, `LEARNING_HELP`, `EXPLICIT_MEMORY_RECALL`, `SENSITIVE_NO_RECALL`, `WEB_REQUIRED`, `ATTACHMENT_GROUNDED`, `RAG_EXPLICIT`.
- `BehaviorAnalysisLevel`: `RULE_ONLY`, `LIGHTWEIGHT_MODEL`, `DEFERRED_DEEP`.
- `TurnPlan`: immutable plan with foreground booleans and model-call budget.
- `TurnPlanService.plan()` using `SearchPolicy`, `MemoryPolicy`, `classify_user_message()`, attachment presence, `use_rag`, `use_web_search`, and `SearchMode`.

Modify `OrchestrationService.execute()` to compute the plan immediately after `last_user_msg` and `RunContext` are available. Use the plan to decide whether to start `classify_dialogue_policy()`, whether prompt assembly may query long-term memory, whether web query rewrite is allowed, and whether suggestions are required. Keep `SearchPolicy`/`TutorAgent` as the search authority; the turn plan should record the result rather than bypass privacy modes.

Modify `ConversationContextService.build_conversation_context()` to accept an optional `allow_long_term_memory_query` and `memory_decision_override`. Default to current behavior for compatibility. When long-term query is skipped by plan, still include hot/working snapshot and log `orchestration.long_term_memory_skipped` with a safe reason.

Modify `MemoryQueryTool.execute()` only if needed to expose trace/model counters. Do not weaken existing permission checks.

Modify `config.py` with feature flags and defaults:

- `enable_turn_plan_runtime: bool = False` for rollout.
- `foreground_model_call_budget_general: int = 2`.
- `foreground_model_call_budget_learning: int = 3`.
- `enable_policy_classifier_for_general_chat: bool = False`.
- `enable_sync_long_term_memory_for_general_chat: bool = False`.

#### Expected File Tree After Phase 2

Cumulative tree after Phase 2:

```text
backend/
├── config.py                            [modified]
├── policies/
│   └── memory_policy.py                 [modified if new reason codes are needed]
├── services/
│   ├── orchestration_service.py         [modified]
│   ├── conversation_context_service.py  [modified]
│   ├── turn_latency_trace.py            [modified]
│   └── turn_plan_service.py             [new]
tests/
└── backend/
    ├── test_turn_plan_service.py        [new]
    ├── test_conversation_context_service.py [modified]
    ├── test_orchestration_service.py    [modified]
    └── test_memory_policy.py            [modified if reason codes change]
```

#### Work List

1. [ ] Create `backend/services/turn_plan_service.py`.
   - [ ] Add proposed `TurnRoute`, `BehaviorAnalysisLevel`, and `TurnPlan`.
   - [ ] Add proposed `TurnPlanService.plan()` using deterministic policy inputs.
   - [ ] Add safe reason codes for skipped policy classifier, skipped long-term memory, and required suggestions.
2. [ ] Modify `Settings` in `backend/config.py`.
   - [ ] Add `enable_turn_plan_runtime`.
   - [ ] Add foreground model budget settings.
   - [ ] Add policy-classifier and long-term-memory general-chat toggles.
3. [ ] Modify `ConversationContextService.build_conversation_context()` in `backend/services/conversation_context_service.py`.
   - [ ] Add optional `allow_long_term_memory_query` defaulting to `None` or current behavior.
   - [ ] Preserve existing `MemoryPolicy` deny behavior for greeting and sensitive queries.
   - [ ] Log safe skip reason when plan denies foreground long-term memory.
4. [ ] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [ ] Compute `TurnPlan` after search routing.
   - [ ] Start `classify_dialogue_policy()` only when the plan allows it or when rollout is disabled.
   - [ ] Pass long-term memory permission into `_node_prompt_assembly()`.
   - [ ] Record model budget decisions into `TurnLatencyTrace`.
5. [ ] Add `tests/backend/test_turn_plan_service.py`.
   - [ ] Assert greeting uses `STATIC_GREETING` and no foreground model budget beyond static reply.
   - [ ] Assert general chat does not require policy classifier by default.
   - [ ] Assert explicit memory recall allows foreground long-term memory.
   - [ ] Assert `search_mode=never` keeps external search forbidden even if text asks for latest news.
6. [ ] Extend `tests/backend/test_conversation_context_service.py`.
   - [ ] Assert planned denial of long-term memory prevents `MemoryQueryTool.execute()`.
   - [ ] Assert explicit recall still calls memory query when allowed.
7. [ ] Extend `tests/backend/test_orchestration_service.py`.
   - [ ] Assert general non-RAG turn does not call `classify_dialogue_policy()` when `enable_turn_plan_runtime=True`.
   - [ ] Assert legacy behavior remains available when the feature flag is disabled.

#### Test Plan

Use unit tests for the deterministic turn planner, context-service memory gating, and orchestration integration. Mock settings with `monkeypatch` or direct settings assignment following existing test conventions. Avoid live model calls. Verify that the new plan does not change privacy behavior for `search_mode=never`, attachment-first auto mode, greeting short-circuit, or sensitive memory denial.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_plan_service.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_memory_policy.py tests/backend/test_agent_foundations.py -q
```

#### Expected Output / Result

When the feature flag is enabled, ordinary non-RAG questions have a deterministic foreground plan and do not automatically spend a model call on policy classification or long-term memory. Explicit recall, sensitive recall rules, Web Search, attachments, and legacy mode remain compatible.

#### Testing Script

##### Act 01: Plan A General Question

Create a `TurnPlanService` and pass a non-RAG message such as `請簡單解釋什麼是成長型思維。` with `search_mode=never`.

Pass condition: the plan allows main answer and suggestions, denies policy classifier by default, and denies synchronous long-term memory unless the compatibility flag is off.

##### Act 02: Plan Explicit Recall

Pass `你還記得我之前提過的學習偏好嗎？`.

Pass condition: the plan route is explicit memory recall and foreground long-term memory is allowed through deterministic `MemoryPolicy`.

##### Act 03: Preserve Legacy Rollout

Run `OrchestrationService.execute()` with `enable_turn_plan_runtime=False`.

Pass condition: existing policy classifier behavior and current tests remain unchanged.

#### Gate to Enter the Next Phase

The next phase must not start until these commands pass:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_plan_service.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_memory_policy.py tests/backend/test_agent_foundations.py -q
```

Retain one test run showing both feature-flag enabled and disabled behavior. If a privacy or memory isolation test fails, stop and fix before proceeding.

#### Phase Commit

Commit message:

```text
feat(backend): add deterministic chat turn planning
```

Stage only Phase 2 files and hunks:

```text
backend/config.py
backend/policies/memory_policy.py
backend/services/orchestration_service.py
backend/services/conversation_context_service.py
backend/services/turn_latency_trace.py
backend/services/turn_plan_service.py
tests/backend/test_turn_plan_service.py
tests/backend/test_conversation_context_service.py
tests/backend/test_orchestration_service.py
tests/backend/test_memory_policy.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): add deterministic chat turn planning"
git show --stat --oneline --summary HEAD
```

Do not commit if the gate fails.

### Phase 3: Parallelize Required Foreground Work Without Changing SSE Semantics

#### Problem

Even after planning, required foreground work can still run in a waterfall: search routing, turn intake, hot memory loading, optional policy classification, optional Web Search, prompt assembly, main model, suggestions. The user wants behavior analysis, short-term memory, necessary prompt, main answer, and suggestions in the current turn. The latency win must therefore come from parallel execution and bounded waits, not from removing foreground work.

Phase 3 is intentionally data-dependent. It must start from the Phase 1/2 trace and benchmark report, not from an assumption that all foreground work should be parallelized. The implementation must identify which synchronous stages materially delay `main_model_started` or `first_answer_delta` and parallelize only those stages whose dependencies and failure semantics are clear.

#### Assumptions

SSE event order must remain client-compatible. Early `metadata`, `status`, and `action` events should continue to appear before slow work completes. Foreground behavior analysis means fast/current-turn behavioral signals and route/style decisions, not full EDF evaluation; full learner-state updates remain durable background work. If Redis or memory ingestion fails, the answer should still proceed with safe fallback state and logs.

#### Solution

Introduce a foreground task coordinator inside `OrchestrationService.execute()` or as a proposed `ForegroundTurnCoordinator`. It should start independent tasks as early as possible: turn intake, hot memory snapshot/context preparation, policy classifier when allowed, and Web Search when required. The coordinator should gather required results with phase-specific timeouts and safe fallbacks. Prompt assembly should accept preloaded hot-memory/learner-state data so it does not reread Redis unnecessarily.

Because current prompt assembly loads hot memory internally, this phase adds a reusable `TurnContextSnapshot` or extends `ConversationContextService` to accept preloaded snapshot data. The implementation must keep run-local state explicit and avoid hidden shared instance fields.

#### Implementation

> Context: Add Google-style docstrings for every new public module, class, and function. Document task ownership, cancellation behavior, timeout semantics, and fallback data for every foreground task. Inline comments should explain why tasks are safe to run concurrently and which state is run-local. Structured logs must include `run_id`, `conversation_id`, task name, outcome, elapsed milliseconds, timeout/fallback reason, and must exclude raw user text and memory contents.

Add proposed `backend/services/foreground_turn_coordinator.py` if keeping orchestration readable requires it. The coordinator should define `ForegroundTaskResult`, `TurnContextSnapshot`, and a method such as `run_preflight()` that returns:

- search decision already computed by orchestration, or accepted as input.
- `turn_intake_result`.
- hot memory snapshot text.
- learner state and roleplay state when available.
- optional policy classification result.
- optional Web Search context and sources.
- safe skip/fallback reason codes.

Alternatively, if the implementation remains small, keep this as private helpers in `orchestration_service.py`, but the plan preference is a service because the current file is already large.

Modify `ConversationContextService.build_conversation_context()` to accept an optional preloaded snapshot object. If provided, it must not call `snapshot_loader()` or `store.get_hot_memory()` again for the same fields.

Modify `TurnIntakeService.process()` to expose separable methods if needed:

- `record_interaction_timestamp()`.
- `ingest_user_evidence()`.
- `apply_roleplay_state()`.

Keep `process()` for compatibility and have it call the smaller methods. This allows the coordinator to run timestamp/ingestion/roleplay with clear timeout behavior.

Modify `OrchestrationService.execute()` to:

- emit early status/action events as now.
- compute `TurnPlan`.
- start foreground tasks using `asyncio.create_task()`.
- await only required task results before prompt assembly.
- cancel or collect completed optional tasks before terminal completion to avoid leaking tasks.
- preserve greeting short-circuit behavior, with only required lightweight intake if the product still wants behavior analysis for greetings.

#### Expected File Tree After Phase 3

Cumulative tree after Phase 3:

```text
backend/
├── services/
│   ├── orchestration_service.py             [modified]
│   ├── conversation_context_service.py      [modified]
│   ├── turn_intake_service.py               [modified]
│   ├── turn_latency_trace.py                [modified]
│   ├── turn_plan_service.py                 [modified]
│   └── foreground_turn_coordinator.py       [new if extracted]
tests/
└── backend/
    ├── test_foreground_turn_coordinator.py  [new if extracted]
    ├── test_turn_intake_service.py          [modified]
    ├── test_conversation_context_service.py [modified]
    └── test_orchestration_service.py        [modified]
```

#### Work List

1. [ ] Review Phase 1/2 evidence before editing runtime code.
   - [ ] Read the saved baseline and TurnPlan-enabled benchmark outputs from `scripts/performance/benchmark_chat_latency.py`.
   - [ ] Identify the top foreground contributors to `main_model_started` and `first_answer_delta`.
   - [ ] Record the chosen Phase 3 target stages in the implementation notes or PR description before changing orchestration.
2. [ ] Create `backend/services/foreground_turn_coordinator.py` if extraction is chosen.
   - [ ] Add proposed `ForegroundTaskResult` and `TurnContextSnapshot`.
   - [ ] Add proposed `ForegroundTurnCoordinator.run_preflight()`.
   - [ ] Add timeout/fallback result construction without raw content logging.
3. [ ] Modify `TurnIntakeService` in `backend/services/turn_intake_service.py`.
   - [ ] Extract proposed `record_interaction_timestamp()`.
   - [ ] Extract proposed `ingest_user_evidence()`.
   - [ ] Extract proposed `apply_roleplay_state()`.
   - [ ] Keep `process()` as a compatibility wrapper.
4. [ ] Modify `ConversationContextService.build_conversation_context()` in `backend/services/conversation_context_service.py`.
   - [ ] Add optional preloaded `TurnContextSnapshot` parameter.
   - [ ] Skip duplicate snapshot and hot-memory store reads when preloaded data exists.
   - [ ] Preserve prompt safety and learner-understanding rules.
5. [ ] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [ ] Start allowed foreground tasks concurrently after early metadata/status/action events.
   - [ ] Await task results with explicit timeouts and fallback reason codes.
   - [ ] Pass preloaded context into `_node_prompt_assembly()`.
   - [ ] Ensure all created tasks are awaited, cancelled, or explicitly transferred to durable background work.
6. [ ] Add or extend tests.
   - [ ] `tests/backend/test_foreground_turn_coordinator.py`: assert independent tasks run concurrently by controlled sleep ordering.
   - [ ] `tests/backend/test_turn_intake_service.py`: assert extracted methods preserve `process()` behavior.
   - [ ] `tests/backend/test_conversation_context_service.py`: assert preloaded snapshot prevents duplicate loader/store calls.
   - [ ] `tests/backend/test_orchestration_service.py`: assert first visible events still precede preflight completion.

#### Test Plan

Use controlled async sleeps to prove concurrency without relying on wall-clock production timings. Mock Redis, memory ingestion, policy classifier, and Web Search. Assert that duplicate memory reads are eliminated when a snapshot is preloaded. Assert that task timeout produces safe fallback and the stream still reaches terminal completion.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_foreground_turn_coordinator.py tests/backend/test_turn_intake_service.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py -q
```

If no separate coordinator file is created, replace `test_foreground_turn_coordinator.py` with the orchestration tests that cover the private helper behavior.

#### Expected Output / Result

Required foreground work runs concurrently where data dependencies allow. Prompt assembly no longer performs duplicate hot-memory reads when a preloaded snapshot is available. First visible SSE events remain early, main model start occurs sooner for general non-RAG turns, and fallback behavior remains safe when a foreground task fails or times out.

#### Testing Script

##### Act 01: Concurrent Preflight

Configure mocked behavior analysis, hot-memory snapshot, and policy classifier tasks with known sleeps.

Pass condition: total preflight elapsed time is close to the slowest single task rather than the sum of all task delays.

##### Act 02: No Duplicate Hot Memory Read

Call prompt assembly with a preloaded snapshot and a mocked `snapshot_loader`.

Pass condition: the final prompt includes the preloaded working memory and `snapshot_loader` is not awaited.

##### Act 03: Timeout Fallback Still Answers

Make foreground memory ingestion hang beyond its configured timeout while the LLM stream is mocked to return an answer.

Pass condition: the stream emits answer content and exactly one terminal event, and logs a safe timeout reason.

#### Gate to Enter the Next Phase

The next phase must not start until these commands pass:

```bash
python scripts/performance/benchmark_chat_latency.py --mode mocked --runs 10 --warmup 2 --output /tmp/areqa-phase2-before-parallelization.json
PYTHONPATH=. pytest tests/backend/test_turn_intake_service.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_runtime_contracts.py -q
PYTHONPATH=. pytest tests/backend/test_chat_latency_benchmark.py -q
```

Retain the Phase 2 benchmark output, a short note identifying the measured bottlenecks selected for Phase 3, a test log showing the concurrency assertion, and one trace snapshot with improved main-model-start timing in mocked conditions. If Phase 2 data does not identify a meaningful preflight bottleneck, narrow Phase 3 to duplicate-read removal, task cleanup, and observability hardening. If any task leaks or terminal-event behavior changes, stop and fix before proceeding.

#### Phase Commit

Commit message:

```text
refactor(backend): parallelize chat foreground preflight
```

Stage only Phase 3 files and hunks:

```text
backend/services/foreground_turn_coordinator.py
backend/services/orchestration_service.py
backend/services/conversation_context_service.py
backend/services/turn_intake_service.py
backend/services/turn_latency_trace.py
backend/services/turn_plan_service.py
tests/backend/test_foreground_turn_coordinator.py
tests/backend/test_turn_intake_service.py
tests/backend/test_conversation_context_service.py
tests/backend/test_orchestration_service.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "refactor(backend): parallelize chat foreground preflight"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 4: Optimize Foreground Suggestions And Live Latency Gates

#### Problem

The user wants suggestions to remain part of the current turn. The current `PostTurnService.suggestion_events()` waits for `SuggestionService.generate_suggestions()` after the answer accumulator, so total completion time depends on a second model/service call. If suggestions remain synchronous, they need a bounded, cache-aware, and optionally lightweight path. The system also needs live and mocked acceptance gates so future changes do not reintroduce excessive foreground model calls.

#### Assumptions

The frontend expects `event: suggestions` and `event: done` compatibility. Suggestions may be generated from the answer accumulator, the user query, and optional sources, but must not expose hidden prompts, memory internals, or raw chain-of-thought. If high-quality suggestions require a model for certain educational turns, the model may still be used within budget and timeout. If suggestion generation fails, `done` with an empty list is acceptable and already matches current fallback behavior.

#### Solution

Add a `SuggestionPlan` or extend `TurnPlan` to choose one of three foreground suggestion strategies: `template`, `lightweight_model`, or `full_model`. General chat can use templates or lightweight models. Learning help may use the current generator with a short timeout. Web/source-grounded turns may use sources but must remain within the configured budget. Add cache keys for deterministic suggestion inputs where useful. Update benchmarks and tests to assert max foreground model-call counts per route.

This phase answers the model-call question in code: model-backed suggestions are not deleted; they are selected intentionally when their value justifies their latency.

#### Implementation

> Context: Add Google-style docstrings for every new public module, class, and function. Document suggestion strategy selection, fallback order, cache key privacy, and timeout semantics. Inline comments should explain only non-obvious quality/speed tradeoffs. Structured logs must include `run_id`, `conversation_id`, suggestion strategy, count, latency, cache status, timeout/fallback reason, and must exclude raw answer text and user text.

Modify `PostTurnService.suggestion_events()` to accept a suggestion strategy from the turn plan and a timeout. Keep current behavior as the legacy default. Add safe structured logs for `orchestration.suggestions_completed`, `orchestration.suggestions_timeout`, and `orchestration.suggestions_failed`.

If `SuggestionService` is in `src/main/python/services/suggestion_service.py`, inspect and modify it to support a lightweight/template path without changing its existing public method unexpectedly. Prefer adding a new method such as `generate_fast_suggestions()` or a strategy parameter. If the service already has deterministic generation helpers, reuse them.

Extend `scripts/performance/benchmark_chat_latency.py` so mocked and live reports include `suggestions_completed_ms` and foreground model-call counters when server trace data is available. The live script should still work without trace data.

Add or update tests to cover template suggestions, model suggestions, timeout fallback, done event compatibility, and benchmark reporting.

#### Expected File Tree After Phase 4

Cumulative tree after Phase 4:

```text
backend/
├── services/
│   ├── post_turn_service.py             [modified]
│   ├── orchestration_service.py         [modified]
│   ├── turn_plan_service.py             [modified]
│   └── turn_latency_trace.py            [modified]
src/
└── main/
    └── python/
        └── services/
            └── suggestion_service.py    [modified if strategy support is needed]
scripts/
└── performance/
    └── benchmark_chat_latency.py        [modified]
tests/
└── backend/
    ├── test_post_turn_service.py        [modified]
    ├── test_orchestration_service.py    [modified]
    ├── test_chat_latency_benchmark.py   [modified]
    └── test_suggestion_service.py       [new if service strategy is added]
```

#### Work List

1. [ ] Inspect `src/main/python/services/suggestion_service.py`.
   - [ ] Identify whether a deterministic/template path already exists.
   - [ ] Add proposed `generate_fast_suggestions()` or a strategy parameter if no fast path exists.
2. [ ] Modify `TurnPlan` in `backend/services/turn_plan_service.py`.
   - [ ] Add proposed suggestion strategy field.
   - [ ] Map routes to `template`, `lightweight_model`, or `full_model`.
3. [ ] Modify `PostTurnService.suggestion_events()` in `backend/services/post_turn_service.py`.
   - [ ] Accept strategy, timeout, and optional trace.
   - [ ] Return `event: done` with empty suggestions on timeout/failure.
   - [ ] Log safe strategy and latency events.
4. [ ] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [ ] Pass planned suggestion strategy into `_node_post_generation()`.
   - [ ] Record suggestion model budget usage in trace.
5. [ ] Modify `scripts/performance/benchmark_chat_latency.py`.
   - [ ] Add optional suggestion completion metric.
   - [ ] Preserve compatibility when trace data is absent.
6. [ ] Add or extend tests.
   - [ ] `tests/backend/test_post_turn_service.py`: timeout fallback and strategy pass-through.
   - [ ] `tests/backend/test_orchestration_service.py`: planned strategy reaches post generation.
   - [ ] `tests/backend/test_chat_latency_benchmark.py`: report includes suggestion timing when available.
   - [ ] `tests/backend/test_suggestion_service.py`: fast suggestions return bounded count without model calls if implemented.

#### Test Plan

Use mocked suggestion services to validate strategy selection and timeout behavior. Use benchmark unit tests for reporting. If a real `SuggestionService` fast path is added, test it with deterministic inputs and no external model calls. Existing accumulator and done-event tests must continue to pass.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py tests/backend/test_chat_latency_benchmark.py -q
PYTHONPATH=. pytest tests/backend/test_suggestion_service.py -q
```

Skip the second command only if no separate suggestion-service test file is created.

#### Expected Output / Result

Suggestions remain foreground but become strategy-driven, bounded, and traceable. General non-RAG turns can complete suggestions without an additional heavyweight model call when the plan selects a fast strategy. Failures and timeouts produce `done` with an empty suggestion list and do not break terminal SSE behavior.

#### Testing Script

##### Act 01: Fast Suggestions

Run post-generation with a general-chat turn plan and a deterministic answer accumulator.

Pass condition: suggestions are returned or empty within the configured timeout, and no full-model suggestion call is made.

##### Act 02: Suggestion Timeout

Mock the suggestion service to sleep beyond the configured timeout.

Pass condition: `event: done` is emitted with `suggestions: []`, and `orchestration.suggestions_timeout` is logged once.

##### Act 03: Benchmark Suggestion Timing

Run the mocked benchmark report generation.

Pass condition: the report renders suggestion timing or remains backward-compatible when no trace data exists.

#### Gate to Enter the Next Phase

This is the final implementation phase gate before cross-phase acceptance:

```bash
PYTHONPATH=. pytest tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py tests/backend/test_chat_latency_benchmark.py -q
PYTHONPATH=. pytest tests/backend/test_runtime_contracts.py tests/backend/test_stream_endpoint.py -q
```

Retain evidence showing timeout fallback and done-event compatibility. If suggestion quality requirements conflict with timeout limits, document the route-specific tradeoff before changing the budget.

#### Phase Commit

Commit message:

```text
feat(backend): bound foreground suggestion generation
```

Stage only Phase 4 files and hunks:

```text
backend/services/post_turn_service.py
backend/services/orchestration_service.py
backend/services/turn_plan_service.py
backend/services/turn_latency_trace.py
src/main/python/services/suggestion_service.py
scripts/performance/benchmark_chat_latency.py
tests/backend/test_post_turn_service.py
tests/backend/test_orchestration_service.py
tests/backend/test_chat_latency_benchmark.py
tests/backend/test_suggestion_service.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): bound foreground suggestion generation"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Cross-Phase Regression and Final Acceptance

Run the full focused regression suite after all phase commits:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_latency_trace.py tests/backend/test_turn_plan_service.py tests/backend/test_foreground_turn_coordinator.py tests/backend/test_turn_intake_service.py tests/backend/test_conversation_context_service.py tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py tests/backend/test_runtime_contracts.py tests/backend/test_stream_endpoint.py tests/backend/test_agent_foundations.py tests/backend/test_memory_policy.py tests/backend/test_memory_query_tool.py tests/backend/test_web_search_tool.py tests/backend/test_chat_latency_benchmark.py -q
python scripts/performance/benchmark_chat_latency.py --mode mocked --runs 10 --warmup 2 --output /tmp/areqa-pipeline-improvement.json
```

If no separate `tests/backend/test_foreground_turn_coordinator.py` or `tests/backend/test_suggestion_service.py` exists because the implementation stayed inside existing services, omit only those nonexistent files and document why.

For live validation, run only in an environment with a test account and configured backend URL/token:

```bash
python scripts/performance/benchmark_chat_latency.py --mode live --runs 5 --warmup 1 --backend-url "$BACKEND_API_URL" --token "$BENCHMARK_AUTH_TOKEN" --output /tmp/areqa-pipeline-live.json
```

Acceptance outcomes:

- Non-RAG general chat uses a deterministic turn plan and does not synchronously enter RAG logic.
- General non-RAG turns reduce foreground model calls compared with the traced baseline while preserving main answer and foreground suggestions.
- Explicit recall still allows memory query through deterministic `MemoryPolicy`.
- `search_mode=never` still performs zero external search calls.
- `search_mode=auto` and Web-required queries still respect `SearchPolicy`/`TutorAgent` and `ToolBudgetTracker`.
- Greeting/static low-information behavior still short-circuits safely.
- SSE remains compatible: metadata/status/action events can appear early, answer deltas stream, suggestions/done remain valid, and exactly one terminal `data: [DONE]` is emitted.
- Structured logs are privacy-safe and contain safe reason codes, phase timings, route, model-call budget, and fallback outcomes.
- Mock benchmark shows expected TTFT and completion-time improvement; live benchmark provides production evidence before rollout.

Remaining risks and mitigations:

- Suggestion quality may drop if a fast strategy replaces the current generator. Mitigate by route-specific strategy selection and A/B comparison.
- Disabling general foreground long-term memory may reduce personalization for some questions. Mitigate with explicit recall detection, hot-memory snapshots, and trace-backed rollout.
- Parallel foreground work can introduce task leaks or cancellation bugs. Mitigate with explicit task ownership tests and runtime-contract tests.
- Model-call budgets can underfit future product requirements. Mitigate by making budgets configurable and logging budget exhaustion with safe reason codes.

Final repository checks:

```bash
git status --short
git log --oneline -4
```

The final status must show no planned implementation files left unstaged or uncommitted, except unrelated user changes that were intentionally preserved. The log must contain the phase commits in order:

```text
feat(backend): add chat turn latency tracing
feat(backend): add deterministic chat turn planning
refactor(backend): parallelize chat foreground preflight
feat(backend): bound foreground suggestion generation
```

No phase may be considered complete without its gate evidence and phase commit.
