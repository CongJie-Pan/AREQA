# AREQA Pipeline Processing Improvement Plan

> Implementation Plan: Faster Non-RAG Chat Runtime With Controlled Model Budgets

This plan improves AREQA chat response speed without removing the product pipeline the user wants to keep. The current code shows that `/api/v1/stream` enters `OrchestrationService.execute()` and then synchronously performs routing, turn intake, optional policy classification, optional RAG/Web work, prompt assembly with hot and long-term memory, main LLM streaming, synchronous suggestions, and post-turn durable job dispatch. Internal RAG is already disabled unless `ENABLE_INTERNAL_RAG=true`, and the user confirmed RAG is not part of the current product path. Therefore, this plan optimizes the non-RAG path first, preserves Web Search when policy requires it, preserves behavior analysis and suggestions in the foreground, and keeps learner-state updates, reflection, compaction, and long-term organization in durable background work.

The phase order is deliberate: first add measurement, then introduce a deterministic turn plan and model-call budget, then run baseline-versus-TurnPlan experiments, then optimize the measured long-term-memory bottleneck before refining memory quality and retrieval policy. Phase 3 must not be treated as a speculative rewrite or broad parallelization phase. It should be driven by Phase 1 and Phase 2 evidence: the production trace showed that slow `prompt_assembly` was dominated by synchronous `long_term_memory`, while provider first token was fast. This avoids guessing where latency comes from and avoids over-agentification. The existing `ConversationRuntime`, `RunContext`, `ConversationRunState`, `SearchPolicy`, `MemoryPolicy`, `TutorAgent`, `ToolRegistry`, `ToolBudgetTracker`, and latency benchmark script should be reused rather than replaced.

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

2026-07-19 production trace update: the first deployed trace review identified the slow tail as explicit memory recall waiting on synchronous long-term memory inside prompt assembly. The reviewed slow traces had `provider_first_token_ms` below `500 ms`, while `long_term_memory` took about `3.9s` to `4.1s` and `prompt_assembly` took about `4.4s` to `4.6s`. Therefore Phase 3 should be a bounded explicit-recall memory timeout/cache experiment before any broad foreground parallelization. Suggestions remain enabled and observed, but they are not an optimization target in this plan revision.

## 2026-07-19 Experiment Update

Phase 1 and Phase 2 have been implemented and validated. The relevant implementation commit is `c96d7f1 feat(backend): add chat turn planning telemetry`, and the production trace-summary follow-up commit is `8565832 feat(backend): add production turn trace summaries`.

Observed client-visible production latency improved after TurnPlan rollout:

| Run | Runs | First content median | First content p95 | Completed median | Completed p95 |
|---|---:|---:|---:|---:|---:|
| Original production baseline | 5 | `7102.62 ms` | `7948.35 ms` | `8814.57 ms` | `9727.81 ms` |
| TurnPlan initial production run | 5 | `3404.74 ms` | `11877.90 ms` | `5359.88 ms` | `13683.75 ms` |
| TurnPlan + production trace run | 20 | `3289.88 ms` | `7237.36 ms` | `5421.39 ms` | `8808.76 ms` |

The 20-run result shows that TurnPlan reduced normal latency and did not reproduce the initial small-sample p95 regression. Server-side production trace then identified the remaining slow tail as route-specific: `EXPLICIT_MEMORY_RECALL` requests waited for synchronous long-term memory inside prompt assembly. In the copied log window, slow explicit-recall traces had `time_to_first_answer_ms` around `6054 ms` to `6537 ms`, but `provider_first_token_ms` stayed low at `395 ms` to `497 ms`; the answer model was not the dominant delay.

The next phases are updated accordingly:

- Phase 3 should first bound and cache explicit-recall long-term memory, because that is the measured p95/root-cause path.
- Phase 4 should refine long-term memory quality and retrieval policy, because `prompt_assembly` is only expensive when it blocks on long-term memory; suggestions remain enabled but are not optimized in this plan revision.
- Broad preflight parallelization remains a later option only if new traces show independent required tasks are still the top bottleneck after memory timeout/cache.

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

Status: completed on 2026-07-19. Gate evidence: `phase1_gate_output.txt` recorded `28 passed, 2 skipped`; the later focused production-trace summary regression recorded `24 passed, 2 skipped`. The implementation now emits safe `orchestration.turn_trace_completed`, `orchestration.turn_trace_summary`, and slow-request `orchestration.turn_trace_slow` logs.

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

1. [x] Create `backend/services/turn_latency_trace.py`.
   - [x] Add proposed `PhaseTiming`, `ModelCallCounter`, and `TurnLatencyTrace`.
   - [x] Add `TurnLatencyTrace.mark()` and `TurnLatencyTrace.snapshot()` with stable safe phase names.
   - [x] Add counters for foreground model/tool usage including `policy_classifier`, `main_answer`, `suggestions`, `web_search`, and `memory_query`.
   - [x] Add `TurnLatencyTrace.diagnostic_summary()` for production-readable phase durations and slow-reason classification.
2. [x] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [x] Instantiate `TurnLatencyTrace` after `self.runtime.start_session()`.
   - [x] Mark each current foreground phase without changing ordering.
   - [x] Emit one safe structured log `orchestration.turn_trace_completed` before terminal completion.
   - [x] Emit `orchestration.turn_trace_summary` and `orchestration.turn_trace_slow` when production trace summary is enabled.
3. [x] Modify `ConversationStreamService.stream()` in `backend/services/conversation_stream_service.py`.
   - [x] Add optional `trace` parameter.
   - [x] Mark provider request start, first answer delta, stream completion, and stream failure.
4. [x] Modify `PostTurnService.suggestion_events()` in `backend/services/post_turn_service.py`.
   - [x] Add optional `trace` parameter and record suggestion start/finish/failure.
5. [x] Add `tests/backend/test_turn_latency_trace.py`.
   - [x] Assert safe metadata behavior.
   - [x] Assert mark-once, measure, counters, diagnostic summary, and slow-phase classification.
6. [x] Extend `tests/backend/test_orchestration_service.py`.
   - [x] Assert a normal non-RAG turn logs `orchestration.turn_trace_completed`.
   - [x] Assert the log contains safe phase names and does not contain the raw user query.
   - [x] Assert the production summary fields are logged.

#### Test Plan

Run focused backend tests around trace behavior and existing orchestration contracts. Mock the LLM stream, suggestion service, and memory store to avoid external calls. Use `caplog` to assert event names and safe fields, not formatted sentences. Existing greeting, accumulator, search-mode, attachment, and durable-job tests must still pass.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_latency_trace.py tests/backend/test_orchestration_service.py tests/backend/test_post_turn_service.py -q
PYTHONPATH=. pytest tests/backend/test_chat_latency_benchmark.py -q
```

#### Expected Output / Result

Every chat run produces one privacy-safe structured trace log with phase durations and aggregate model/tool counters. User-facing SSE output remains compatible. No new model calls are added.

Actual 2026-07-19 result: local gates passed, production trace deployment succeeded, and copied backend logs showed phase attribution for real requests. The trace successfully separated provider first-token latency from pre-model work. In slow explicit-recall traces, `provider_first_token_ms` stayed below `500 ms`, while `prompt_assembly` and `long_term_memory` dominated.

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

Actual gate evidence retained:

- `docs/worklog/202607/2026_07_19_experiment/phase1_gate_output.txt`: `28 passed, 2 skipped`.
- Focused production trace summary regression after deployment: `pytest tests/backend/test_turn_latency_trace.py tests/backend/test_config.py tests/backend/test_orchestration_service.py -q` produced `24 passed, 2 skipped`.

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

Status: completed on 2026-07-19. Gate evidence: `phase2_gate_output.txt` recorded `50 passed, 2 skipped`, and the combined focused regression recorded `47 passed, 2 skipped`. The local trace probe confirmed that TurnPlan-enabled general non-RAG chat dropped foreground completion calls from `2` to `1` and memory tool calls from `1` to `0`.

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

1. [x] Create `backend/services/turn_plan_service.py`.
   - [x] Add proposed `TurnRoute`, `BehaviorAnalysisLevel`, and `TurnPlan`.
   - [x] Add proposed `TurnPlanService.plan()` using deterministic policy inputs.
   - [x] Add safe reason codes for skipped policy classifier, skipped long-term memory, and required suggestions.
2. [x] Modify `Settings` in `backend/config.py`.
   - [x] Add `enable_turn_plan_runtime`.
   - [x] Add foreground model budget settings.
   - [x] Add policy-classifier and long-term-memory general-chat toggles.
3. [x] Modify `ConversationContextService.build_conversation_context()` in `backend/services/conversation_context_service.py`.
   - [x] Add optional `allow_long_term_memory_query` defaulting to current behavior.
   - [x] Preserve existing `MemoryPolicy` deny behavior for greeting and sensitive queries.
   - [x] Log safe skip reason when plan denies foreground long-term memory.
4. [x] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [x] Compute `TurnPlan` after search routing.
   - [x] Start `classify_dialogue_policy()` only when the plan allows it or when rollout is disabled.
   - [x] Pass long-term memory permission into `_node_prompt_assembly()`.
   - [x] Record route/model-call decisions into `TurnLatencyTrace`.
5. [x] Add `tests/backend/test_turn_plan_service.py`.
   - [x] Assert greeting/static and general route behavior.
   - [x] Assert general chat does not require policy classifier by default.
   - [x] Assert explicit memory recall allows foreground long-term memory.
   - [x] Assert `search_mode=never` keeps external search forbidden even if text asks for latest news.
6. [x] Extend `tests/backend/test_conversation_context_service.py`.
   - [x] Assert planned denial of long-term memory prevents `MemoryQueryTool.execute()`.
   - [x] Assert explicit recall still calls memory query when allowed.
7. [x] Extend `tests/backend/test_orchestration_service.py`.
   - [x] Assert general non-RAG turn does not call `classify_dialogue_policy()` when `enable_turn_plan_runtime=True`.
   - [x] Assert legacy behavior remains available when the feature flag is disabled.

#### Test Plan

Use unit tests for the deterministic turn planner, context-service memory gating, and orchestration integration. Mock settings with `monkeypatch` or direct settings assignment following existing test conventions. Avoid live model calls. Verify that the new plan does not change privacy behavior for `search_mode=never`, attachment-first auto mode, greeting short-circuit, or sensitive memory denial.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_plan_service.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_memory_policy.py tests/backend/test_agent_foundations.py -q
```

#### Expected Output / Result

When the feature flag is enabled, ordinary non-RAG questions have a deterministic foreground plan and do not automatically spend a model call on policy classification or long-term memory. Explicit recall, sensitive recall rules, Web Search, attachments, and legacy mode remain compatible.

Actual 2026-07-19 result: TurnPlan-enabled general non-RAG route skipped policy classification and synchronous long-term memory in the controlled trace probe. Production showed first-content median improvement from `7102.62 ms` in the original baseline to `3289.88 ms` in the 20-run TurnPlan + trace run. Explicit memory recall remained intentionally allowed to use long-term memory, and production trace later showed that route is now the main slow-tail target.

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

Actual gate evidence retained:

- `docs/worklog/202607/2026_07_19_experiment/phase2_gate_output.txt`: `50 passed, 2 skipped`.
- `docs/worklog/202607/2026_07_19_experiment/combined_regression_output.txt`: `47 passed, 2 skipped`.
- `docs/worklog/202607/2026_07_19_experiment/turn_plan_trace_probe.json`: disabled route had `completion_create_calls=2` and `memory_query=1`; enabled route had `completion_create_calls=1` and no memory tool calls.

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

### Phase 3: Bound Explicit-Recall Long-Term Memory Before Main Answer

Status: implemented locally on 2026-07-19; production validation pending deployment. Local gate evidence: `pytest tests/backend/test_config.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_turn_latency_trace.py tests/backend/test_memory_query_tool.py tests/backend/test_memory_policy.py -q` produced `41 passed, 2 skipped`.

#### Problem

The 2026-07-19 production trace showed that the remaining slow tail is not a general provider first-token problem. Slow requests were `EXPLICIT_MEMORY_RECALL` routes where prompt assembly waited for synchronous long-term memory. The slow examples had `time_to_first_answer_ms` around `6054 ms` to `6537 ms`, while `provider_first_token_ms` stayed below `500 ms`. In those same traces, `long_term_memory` took `3914 ms` to `4127 ms`, and `prompt_assembly` took `4439 ms` to `4647 ms`.

The current behavior is correct in intent because explicit recall should be allowed to use memory, but it is too expensive as an unbounded foreground wait. If the user asks whether the system remembers something, the system should try to retrieve memory, but it should not delay the first answer indefinitely when memory is slow.

#### Assumptions

Explicit recall remains a protected route: TurnPlan should still allow foreground long-term memory for `EXPLICIT_MEMORY_RECALL`. The optimization is timeout and cache policy, not deleting memory. A timeout fallback must be honest and safe: it may answer from current conversation and hot memory, but it must not claim to have retrieved long-term memory when the memory query timed out.

The first timeout target should be configurable, likely `1500 ms` to `2000 ms`, and should be verified against production trace. If the timeout is too short, recall quality may drop. If it is too long, p95 remains high.

#### Solution

Add a bounded foreground memory-query path for explicit recall. `ConversationContextService.build_conversation_context()` should allow a configurable timeout around long-term memory. On timeout, it should continue prompt assembly with hot-memory/current-context fallback and emit safe structured logs and trace marks.

Add a short-lived cache for repeated explicit-recall memory queries from the same user/session. The cache should reduce repeated GUM/cold-memory work during benchmarks and real conversations where users ask several recall-like questions in a short window. The cache key must not log raw user text; use an existing fingerprint helper or a new safe hash helper.

Broad foreground parallelization is deferred. The trace did not show provider first token as the slow tail; it showed memory blocking before main model start. Therefore this phase focuses on the measured root cause first.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed public module, class, and function. Document timeout semantics, cache-key privacy, fallback honesty, memory-scope invariants, and structured logs. Inline comments should explain only why a timeout fallback is safe for explicit recall and why raw text is excluded from cache/log keys. Structured logs must include `run_id` or `conversation_id` when available, route or memory-scope reason, timeout/cache outcome, elapsed milliseconds, and must exclude raw user text, prompts, memory content, model output, credentials, and sensitive labels.

Modify `Settings` in `backend/config.py` to add configurable memory timeout/cache values:

- `explicit_recall_memory_timeout_ms: int = 2000`.
- `explicit_recall_memory_cache_ttl_seconds: int = 120`.
- `enable_explicit_recall_memory_cache: bool = True`.

Modify `ConversationContextService.build_conversation_context()` in `backend/services/conversation_context_service.py` to accept optional memory timeout/cache controls. When `allow_long_term_memory_query=True`, wrap `MemoryQueryTool.execute()` in `asyncio.wait_for()` using the configured timeout. If timeout occurs, record a safe fallback reason such as `explicit_recall_memory_timeout`, omit retrieved long-term memory, and continue prompt assembly.

Add a small memory-query cache helper. Prefer an in-process bounded TTL cache if Redis semantics are not already available in this service. If using Redis, reuse existing cache abstractions and keep serialization privacy-safe. The cache value may contain retrieved memory context only if the existing memory boundary permits it; otherwise cache only the safe query result envelope needed by prompt assembly.

Modify `TurnLatencyTrace` if needed to add marks/counters for `long_term_memory_timeout`, `memory_query_cache_hit`, and `memory_query_cache_miss`. Production `turn_trace_summary` should make timeout/cache behavior visible.

Modify `OrchestrationService.execute()` only to pass timeout/cache settings or route-specific reason into prompt assembly/context service. Do not change SSE wire format.

#### Expected File Tree After Phase 3

Cumulative tree after Phase 3:

```text
backend/
├── config.py                                [modified]
├── services/
│   ├── orchestration_service.py             [modified]
│   ├── conversation_context_service.py      [modified]
│   ├── turn_latency_trace.py                [modified]
│   └── explicit_memory_cache.py             [new if cache is extracted]
tests/
└── backend/
    ├── test_conversation_context_service.py [modified]
    ├── test_orchestration_service.py        [modified]
    ├── test_turn_latency_trace.py           [modified if trace fields change]
    └── test_config.py                       [modified]
```

#### Work List

1. [x] Modify `Settings` in `backend/config.py`.
   - [x] Add `explicit_recall_memory_timeout_ms`.
   - [x] Add `enable_explicit_recall_memory_cache`.
   - [x] Add `explicit_recall_memory_cache_ttl_seconds`.
2. [x] Modify `ConversationContextService.build_conversation_context()` in `backend/services/conversation_context_service.py`.
   - [x] Wrap allowed long-term memory query in a route-aware timeout.
   - [x] Continue prompt assembly with safe fallback when timeout occurs.
   - [x] Log `orchestration.long_term_memory_timeout` with safe metadata only.
   - [x] Preserve explicit recall permission when memory returns within the timeout.
   - [x] Add an honest system-prompt state when long-term memory times out.
3. [x] Add `backend/services/explicit_memory_cache.py` if extraction is chosen.
   - [x] Add proposed `ExplicitMemoryCache` with safe hashed key construction.
   - [x] Add TTL get/set behavior for explicit-recall memory results.
   - [x] Add safe cache status values `hit`, `miss`, and expired handling.
4. [x] Modify `TurnLatencyTrace` in `backend/services/turn_latency_trace.py`.
   - [x] Record memory timeout and cache status through existing phase marks and tool cache statuses.
   - [x] Ensure `turn_trace_summary` exposes memory timeout/cache outcomes through phases and cache statuses.
5. [x] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [x] Pass route-specific timeout/cache configuration to prompt assembly or context service.
   - [x] Preserve current SSE event ordering and terminal behavior.
6. [x] Extend tests.
   - [x] `tests/backend/test_config.py`: assert new defaults and env override.
   - [x] `tests/backend/test_conversation_context_service.py`: assert timeout fallback continues without retrieved memory.
   - [x] `tests/backend/test_conversation_context_service.py`: assert cache hit avoids a second memory tool call.
   - [x] `tests/backend/test_conversation_context_service.py`: assert cache key privacy.
   - [x] `tests/backend/test_orchestration_service.py`: assert explicit-recall runtime timeout/cache settings are passed into prompt assembly.
   - [x] `tests/backend/test_turn_latency_trace.py`: existing summary tests cover privacy-safe trace output; no trace schema change was required.

#### Test Plan

Use mocked `MemoryQueryTool.execute()` calls to validate success, timeout, failure, and cache-hit behavior. Do not use live memory stores in unit tests. Use `asyncio.sleep()` only with controlled short durations. Assert that timeout fallback does not include fake retrieved memory in the prompt and does not block the stream from answering. Assert that cache keys/logs do not contain raw user text.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_config.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_turn_latency_trace.py -q
PYTHONPATH=. pytest tests/backend/test_memory_query_tool.py tests/backend/test_memory_policy.py -q
```

#### Expected Output / Result

Explicit memory recall still attempts long-term memory, but it no longer blocks first answer beyond the configured timeout. Slow memory produces a safe fallback trace/log and the answer stream still starts. Repeated explicit-recall requests can reuse a short-lived cache when safe, reducing repeated `long_term_memory` latency.

The production target is to reduce explicit-recall `time_to_first_answer_ms` from the observed `6054 ms` to `6537 ms` range toward the configured timeout plus main-model first-token latency. For a `2000 ms` timeout and observed provider first-token below `500 ms`, a reasonable target is first answer under roughly `3000 ms` to `3500 ms` for timeout fallback cases.

#### Testing Script

##### Act 01: Explicit Recall Memory Returns Quickly

Mock `MemoryQueryTool.execute()` to return memory before the timeout for `EXPLICIT_MEMORY_RECALL`.

Pass condition: the final prompt includes retrieved memory and no timeout log is emitted.

##### Act 02: Explicit Recall Memory Times Out

Mock `MemoryQueryTool.execute()` to sleep longer than `explicit_recall_memory_timeout_ms`.

Pass condition: the stream still emits answer content and terminal completion, the final prompt does not claim retrieved long-term memory, and `orchestration.long_term_memory_timeout` is logged once.

##### Act 03: Explicit Recall Cache Hit

Run two equivalent explicit-recall context builds with cache enabled and a stable safe fingerprint.

Pass condition: the second run uses cache-hit status and does not call `MemoryQueryTool.execute()` a second time.

##### Act 04: Cache Key Privacy

Build a cache key from a recall-like user message.

Pass condition: logs and cache metadata contain only hashed/fingerprinted identifiers, not the raw user text.

#### Gate to Enter the Next Phase

The next phase must not start until these commands pass:

```bash
PYTHONPATH=. pytest tests/backend/test_config.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_turn_latency_trace.py tests/backend/test_memory_query_tool.py tests/backend/test_memory_policy.py -q
python scripts/performance/benchmark_chat_latency.py --mode live --runs 20 --warmup 2 --output docs/worklog/202607/2026_07_19_experiment/production_latency_memory_timeout.json
```

Retain the test output, live benchmark output, and copied production `orchestration.turn_trace_summary` / `orchestration.turn_trace_slow` logs. The phase passes only if explicit-recall slow traces show bounded `long_term_memory` wait or safe timeout fallback, and SSE completion remains compatible.

Local implementation gate passed on 2026-07-19 with `41 passed, 2 skipped`. The live benchmark and production trace gate remain pending until this change is deployed.

#### Phase Commit

Commit message:

```text
feat(backend): bound explicit recall memory latency
```

Stage only Phase 3 files and hunks:

```text
backend/config.py
backend/services/conversation_context_service.py
backend/services/explicit_memory_cache.py
backend/services/orchestration_service.py
backend/services/turn_latency_trace.py
tests/backend/test_config.py
tests/backend/test_conversation_context_service.py
tests/backend/test_orchestration_service.py
tests/backend/test_turn_latency_trace.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): bound explicit recall memory latency"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 4: Refine Long-Term Memory Quality And Retrieval Policy

Status: pending. This phase should start only after Phase 3 proves explicit-recall memory timeout/cache reduces the slow first-answer path. Suggestions remain part of the current turn and are intentionally not optimized in this plan revision. Today’s trace shows suggestions are a secondary completion-latency cost, but the measured blocking problem is long-term memory retrieval inside prompt assembly.

#### Problem

`prompt_assembly` appeared to be the longest phase in production traces, but the detailed trace shows that most of that duration is synchronous `long_term_memory`. The prompt string construction itself appears to be roughly hundreds of milliseconds, while long-term memory contributes about `3.9s` to `4.1s` in slow explicit-recall traces.

After Phase 3 bounds the speed problem, the next risk is quality and policy drift: the system needs a clear rule for when long-term memory should be retrieved, when hot/short-term memory is enough, how low-confidence or timed-out memory should affect the prompt, and how the answer should honestly describe memory availability. Without this policy, future changes may either over-retrieve memory and reintroduce latency, or under-retrieve memory and degrade personalization.

#### Assumptions

Suggestions remain foreground and unchanged unless later traces prove they become the top business-critical bottleneck. Long-term memory should not be retrieved for every question. Hot memory, current conversation context, and short-term working memory should satisfy most normal turns. Long-term memory retrieval should be reserved for explicit recall, durable preference personalization, or routes where memory materially changes the answer.

Memory quality must be explicit. The prompt and answer should distinguish retrieved long-term memory, hot/current state, low-confidence memory, memory-not-found, and timeout fallback. The system must not claim to remember something when the query timed out or returned insufficient evidence.

#### Solution

Add a memory retrieval policy layer that makes long-term memory use route-specific, confidence-aware, and observable. This can be implemented by extending `TurnPlan` or adding a dedicated `MemoryRetrievalPlan` with fields such as `memory_tier`, `max_wait_ms`, `requires_long_term_memory`, `fallback_behavior`, and `minimum_confidence`.

The policy should use a tiered retrieval model:

- `HOT_ONLY`: current conversation and hot memory only.
- `WORKING_MEMORY`: short-term or current-session memory.
- `LONG_TERM_BOUNDED`: long-term memory with Phase 3 timeout/cache.
- `DEEP_RECALL_BACKGROUND`: optional deeper retrieval that must not block the first answer.

Prompt assembly should consume the memory plan and memory result envelope, not raw implicit service behavior. The prompt should know whether memory was retrieved, skipped, timed out, cache-hit, or low-confidence, and should apply an honest response instruction for each state.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed public module, class, and function. Document memory-tier semantics, confidence thresholds, fallback wording boundaries, privacy constraints, and prompt assembly ownership. Inline comments should explain only non-obvious memory-scope decisions and why specific routes do or do not retrieve long-term memory. Structured logs must include `run_id` or `conversation_id`, route, memory tier, retrieval outcome, confidence bucket, elapsed milliseconds, and safe fallback reason, while excluding raw user text, prompts, memory contents, model output, credentials, and sensitive labels.

Modify `TurnPlan` or add `MemoryRetrievalPlan` in `backend/services/turn_plan_service.py`. The plan should decide memory tier and wait budget from deterministic route signals, not from an unbounded model call. It should preserve explicit recall and sensitive-memory protections.

Modify `ConversationContextService.build_conversation_context()` in `backend/services/conversation_context_service.py` to accept a memory plan and return a structured memory result envelope. The envelope should separate:

- retrieved memory included.
- memory skipped by route.
- memory timed out.
- memory found but below confidence threshold.
- memory cache hit or miss.

Modify prompt assembly in `backend/services/orchestration_service.py` or `ConversationContextService` so the system prompt receives clear memory-state instructions. Timeout or low-confidence memory should produce honest answer guidance rather than silently pretending recall succeeded.

Extend `TurnLatencyTrace` only if needed to include memory tier and memory result counters in `turn_trace_summary`. Do not add user-visible SSE changes.

Add tests for route-to-memory-tier decisions, low-confidence fallback, timeout fallback copy boundaries, and prompt content boundaries.

#### Expected File Tree After Phase 4

Cumulative tree after Phase 4:

```text
backend/
├── services/
│   ├── conversation_context_service.py  [modified]
│   ├── orchestration_service.py         [modified]
│   ├── turn_plan_service.py             [modified]
│   └── turn_latency_trace.py            [modified if memory summary changes]
tests/
└── backend/
    ├── test_conversation_context_service.py [modified]
    ├── test_orchestration_service.py    [modified]
    ├── test_turn_plan_service.py        [modified]
    └── test_turn_latency_trace.py       [modified if memory summary changes]
```

#### Work List

1. [ ] Modify `TurnPlan` or add proposed `MemoryRetrievalPlan` in `backend/services/turn_plan_service.py`.
   - [ ] Add proposed memory tiers `HOT_ONLY`, `WORKING_MEMORY`, `LONG_TERM_BOUNDED`, and `DEEP_RECALL_BACKGROUND`.
   - [ ] Map general chat to `HOT_ONLY` or `WORKING_MEMORY`.
   - [ ] Map explicit recall to `LONG_TERM_BOUNDED`.
   - [ ] Preserve sensitive no-recall behavior.
2. [ ] Modify `ConversationContextService.build_conversation_context()` in `backend/services/conversation_context_service.py`.
   - [ ] Accept the memory retrieval plan.
   - [ ] Return a structured memory result envelope with retrieval outcome and confidence bucket.
   - [ ] Exclude low-confidence or timed-out memory from prompt evidence.
3. [ ] Modify prompt assembly in `backend/services/orchestration_service.py` or `ConversationContextService`.
   - [ ] Add honest prompt instructions for `retrieved`, `skipped`, `timeout`, `not_found`, and `low_confidence` memory states.
   - [ ] Preserve current answer and SSE behavior.
4. [ ] Modify `TurnLatencyTrace` in `backend/services/turn_latency_trace.py` if memory summary changes.
   - [ ] Record memory tier and retrieval outcome counters.
   - [ ] Keep production summary privacy-safe.
5. [ ] Add or extend tests.
   - [ ] `tests/backend/test_turn_plan_service.py`: assert route-to-memory-tier mapping.
   - [ ] `tests/backend/test_conversation_context_service.py`: assert low-confidence and timeout memory are not injected as retrieved evidence.
   - [ ] `tests/backend/test_orchestration_service.py`: assert prompt assembly receives honest memory-state instructions.
   - [ ] `tests/backend/test_turn_latency_trace.py`: assert memory tier/outcome fields remain safe if added.

#### Test Plan

Use mocked memory-policy and memory-query results to validate route-to-tier mapping, confidence gating, timeout outcome handling, and prompt-state wording. Do not use live memory stores in unit tests. Existing accumulator, suggestions, and done-event tests must continue to pass because suggestions are intentionally preserved.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_plan_service.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_turn_latency_trace.py -q
PYTHONPATH=. pytest tests/backend/test_post_turn_service.py tests/backend/test_runtime_contracts.py -q
```

Skip `tests/backend/test_turn_latency_trace.py` only if no trace schema changes are made.

#### Expected Output / Result

Long-term memory retrieval becomes explicit, tiered, confidence-aware, and honest in prompt assembly. General turns should avoid unnecessary long-term memory retrieval, explicit recall should use bounded retrieval from Phase 3, and timeout/low-confidence states should not be presented as successful recall. Suggestions remain unchanged and foreground-compatible.

#### Testing Script

##### Act 01: General Turn Uses Fast Memory Tier

Create a general non-RAG turn plan for a normal explanatory question.

Pass condition: the memory tier is `HOT_ONLY` or `WORKING_MEMORY`, and long-term memory is not required.

##### Act 02: Explicit Recall Uses Bounded Long-Term Memory

Create an explicit-recall turn plan for a recall-like question.

Pass condition: the memory tier is `LONG_TERM_BOUNDED`, and the wait budget comes from Phase 3 configuration.

##### Act 03: Low-Confidence Memory Is Not Injected

Mock a memory result below the confidence threshold.

Pass condition: prompt assembly does not include it as retrieved evidence and records a safe low-confidence reason.

##### Act 04: Suggestions Remain Compatible

Run the existing post-turn suggestion path without changing suggestion strategy.

Pass condition: current suggestion events and terminal completion behavior remain unchanged.

#### Gate to Enter the Next Phase

This is the final implementation phase gate before cross-phase acceptance:

```bash
PYTHONPATH=. pytest tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py tests/backend/test_chat_latency_benchmark.py -q
PYTHONPATH=. pytest tests/backend/test_turn_plan_service.py tests/backend/test_conversation_context_service.py tests/backend/test_runtime_contracts.py tests/backend/test_stream_endpoint.py -q
python scripts/performance/benchmark_chat_latency.py --mode live --runs 20 --warmup 2 --output docs/worklog/202607/2026_07_19_experiment/production_latency_memory_policy.json
```

Retain evidence showing route-to-memory-tier behavior, honest fallback prompt behavior, suggestion compatibility, and production trace memory outcomes. If memory quality requirements conflict with speed limits, document the route-specific tradeoff before changing the retrieval policy.

#### Phase Commit

Commit message:

```text
feat(backend): refine long-term memory retrieval policy
```

Stage only Phase 4 files and hunks:

```text
backend/services/conversation_context_service.py
backend/services/orchestration_service.py
backend/services/turn_plan_service.py
backend/services/turn_latency_trace.py
tests/backend/test_conversation_context_service.py
tests/backend/test_orchestration_service.py
tests/backend/test_turn_plan_service.py
tests/backend/test_turn_latency_trace.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): refine long-term memory retrieval policy"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Cross-Phase Regression and Final Acceptance

Run the full focused regression suite after all phase commits:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_latency_trace.py tests/backend/test_turn_plan_service.py tests/backend/test_turn_intake_service.py tests/backend/test_conversation_context_service.py tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py tests/backend/test_runtime_contracts.py tests/backend/test_stream_endpoint.py tests/backend/test_agent_foundations.py tests/backend/test_memory_policy.py tests/backend/test_memory_query_tool.py tests/backend/test_web_search_tool.py tests/backend/test_chat_latency_benchmark.py -q
python scripts/performance/benchmark_chat_latency.py --mode mocked --runs 10 --warmup 2 --output /tmp/areqa-pipeline-improvement.json
```

If no separate `backend/services/explicit_memory_cache.py` exists because the implementation stayed inside existing services, omit only that nonexistent file and document why.

For live validation, run only in an environment with a test account and configured backend URL/token:

```bash
python scripts/performance/benchmark_chat_latency.py --mode live --runs 20 --warmup 2 --backend-url "$BACKEND_API_URL" --token "$BENCHMARK_AUTH_TOKEN" --output /tmp/areqa-pipeline-live.json
```

Acceptance outcomes:

- Non-RAG general chat uses a deterministic turn plan and does not synchronously enter RAG logic.
- General non-RAG turns reduce foreground model calls compared with the traced baseline while preserving main answer and foreground suggestions.
- Explicit recall still allows memory query through deterministic `MemoryPolicy`, but the foreground wait is bounded by timeout/cache policy.
- Explicit-recall timeout fallback does not claim retrieved long-term memory when the query exceeded the configured timeout.
- General turns use hot/working memory by default and avoid unnecessary long-term memory retrieval.
- Low-confidence memory is not injected into prompts as retrieved evidence.
- Suggestions remain enabled and compatible, but are not a planned optimization target in this revision.
- `search_mode=never` still performs zero external search calls.
- `search_mode=auto` and Web-required queries still respect `SearchPolicy`/`TutorAgent` and `ToolBudgetTracker`.
- Greeting/static low-information behavior still short-circuits safely.
- SSE remains compatible: metadata/status/action events can appear early, answer deltas stream, suggestions/done remain valid, and exactly one terminal `data: [DONE]` is emitted.
- Structured logs are privacy-safe and contain safe reason codes, phase timings, route, model-call budget, and fallback outcomes.
- Mock benchmark shows expected TTFT and completion-time improvement; live benchmark provides production evidence before rollout.
- Production trace should show explicit-recall `long_term_memory` no longer blocks `time_to_first_answer_ms` past the configured fallback window.

Remaining risks and mitigations:

- Memory recall completeness may drop on timeout. Mitigate by honest fallback copy, short-lived cache, and optional follow-up memory enrichment when late memory arrives.
- Disabling general foreground long-term memory may reduce personalization for some questions. Mitigate with explicit recall detection, hot-memory snapshots, and trace-backed rollout.
- Memory retrieval policy may become too conservative. Mitigate with route-specific metrics for memory hit rate, timeout rate, and user-visible recall accuracy.
- Later parallel foreground work can introduce task leaks or cancellation bugs. Mitigate with explicit task ownership tests and runtime-contract tests only if that later work is reintroduced.
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
feat(backend): bound explicit recall memory latency
feat(backend): refine long-term memory retrieval policy
```

No phase may be considered complete without its gate evidence and phase commit.
