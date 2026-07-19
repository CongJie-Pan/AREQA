# AREQA Pipeline Processing Improvement Plan

> Implementation Plan: Faster Non-RAG Chat Runtime With Controlled Model Budgets

This plan improves AREQA chat response speed without removing the product pipeline the user wants to keep. The current code shows that `/api/v1/stream` enters `OrchestrationService.execute()` and then synchronously performs routing, turn intake, optional policy classification, optional RAG/Web work, prompt assembly with hot and long-term memory, main LLM streaming, synchronous suggestions, and post-turn durable job dispatch. Internal RAG is already disabled unless `ENABLE_INTERNAL_RAG=true`, and the user confirmed RAG is not part of the current product path. Therefore, this plan optimizes the non-RAG path first, preserves Web Search when policy requires it, preserves behavior analysis and suggestions in the foreground, and keeps learner-state updates, reflection, compaction, and long-term organization in durable background work.

The phase order is deliberate: first add measurement, then introduce a deterministic turn plan and model-call budget, then run baseline-versus-TurnPlan experiments, then bound explicit-recall memory latency, then use production evidence to choose the next user-visible bottleneck. Phase 3 must not be treated as a speculative rewrite or broad parallelization phase. It should be driven by Phase 1 and Phase 2 evidence: the production trace showed that slow `prompt_assembly` was dominated by synchronous `long_term_memory`, while provider first token was fast. Phase 4A then added long-term-memory profiling, but the latest production log and user feedback show the next practical bottleneck is the final 1-2 second wait after the main answer, which aligns with synchronous suggestion generation. This avoids guessing where latency comes from and avoids over-agentification. The existing `ConversationRuntime`, `RunContext`, `ConversationRunState`, `SearchPolicy`, `MemoryPolicy`, `TutorAgent`, `ToolRegistry`, `ToolBudgetTracker`, and latency benchmark script should be reused rather than replaced.

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

2026-07-19 production trace update: the first deployed trace review identified the slow tail as explicit memory recall waiting on synchronous long-term memory inside prompt assembly. The reviewed slow traces had `provider_first_token_ms` below `500 ms`, while `long_term_memory` took about `3.9s` to `4.1s` and `prompt_assembly` took about `4.4s` to `4.6s`. Therefore Phase 3 became a bounded explicit-recall memory timeout/cache experiment before any broad foreground parallelization. After Phase 3 and Phase 4A deployment, product feedback indicates the answer path now feels acceptable, while the final completion wait remains visible. Suggestions are therefore promoted to the next optimization target.

## 2026-07-19 Experiment Update

Phase 1 and Phase 2 have been implemented and validated. The relevant implementation commit is `c96d7f1 feat(backend): add chat turn planning telemetry`, and the production trace-summary follow-up commit is `8565832 feat(backend): add production turn trace summaries`.

Observed client-visible production latency improved after TurnPlan rollout:

| Run | Runs | First content median | First content p95 | Completed median | Completed p95 |
|---|---:|---:|---:|---:|---:|
| Original production baseline | 5 | `7102.62 ms` | `7948.35 ms` | `8814.57 ms` | `9727.81 ms` |
| TurnPlan initial production run | 5 | `3404.74 ms` | `11877.90 ms` | `5359.88 ms` | `13683.75 ms` |
| TurnPlan + production trace run | 20 | `3289.88 ms` | `7237.36 ms` | `5421.39 ms` | `8808.76 ms` |
| Phase 3 memory timeout/cache production run | 20 | `3131.11 ms` | `5989.32 ms` | `7251.20 ms` | `10997.05 ms` |

The 20-run result shows that TurnPlan reduced normal latency and did not reproduce the initial small-sample p95 regression. Server-side production trace then identified the remaining slow tail as route-specific: `EXPLICIT_MEMORY_RECALL` requests waited for synchronous long-term memory inside prompt assembly. In the copied log window, slow explicit-recall traces had `time_to_first_answer_ms` around `6054 ms` to `6537 ms`, but `provider_first_token_ms` stayed low at `395 ms` to `497 ms`; the answer model was not the dominant delay.

The next phases are updated accordingly:

- Phase 3 should first bound and cache explicit-recall long-term memory, because that is the measured p95/root-cause path.
- Phase 4A should instrument and benchmark long-term memory retrieval itself, because Phase 3 bounded the wait but did not prove memory can usually complete within the foreground budget.
- Phase 4B should be suspended for now. Phase 4A produced useful instrumentation, but the current product feedback says explicit-recall first-answer latency feels acceptable enough to defer deeper long-term-memory retrieval optimization.
- Phase 5 should become the next implementation priority and improve synchronous suggestion latency, because production trace and user-perceived behavior both point to the final post-answer wait as the current issue.
- Broad preflight parallelization remains a later option only if new traces show independent required tasks are still the top bottleneck after memory timeout/cache.

Phase 3 production validation update: the deployed timeout/cache change improved the user-visible first-answer path but did not improve end-to-end completion latency. Compared with the 20-run TurnPlan + trace run, first-content median improved from `3289.88 ms` to `3131.11 ms`, first-content p95 improved from `7237.36 ms` to `5989.32 ms`, and first visible status median improved from `983.50 ms` to `746.02 ms`. However, completed median regressed from `5421.39 ms` to `7251.20 ms`, and completed p95 regressed from `8808.76 ms` to `10997.05 ms`. This means Phase 3 passed its memory-specific gate but only partially passed the broader user-visible latency gate.

Phase 3 production trace validation later confirmed the memory-specific behavior. The copied deployed trace in `temp/log.md` contains two explicit-recall timeout runs. Both recorded `memory_query:timeout`, and their `long_term_memory` durations were bounded at `2049 ms` and `2000 ms`, down from the pre-Phase-3 slow traces where `long_term_memory` took `3914 ms` to `4127 ms`. Their `prompt_assembly` durations were `2572 ms` and `2524 ms`, down from `4439 ms` to `4647 ms`. Therefore the long-term-memory bottleneck was bounded as intended.

Per-route production split:

| Route | Before Phase 3 first median | After Phase 3 first median | Before Phase 3 completed median | After Phase 3 completed median |
|---|---:|---:|---:|---:|
| `explicit_recall` | `7117.75 ms` | `5356.67 ms` | `8548.30 ms` | `7961.18 ms` |
| `general` | `3313.10 ms` | `3208.14 ms` | `5418.08 ms` | `6482.48 ms` |
| `sensitive` | `2521.37 ms` | `2307.63 ms` | `4634.09 ms` | `4788.64 ms` |

The split supports the Phase 3 diagnosis: explicit recall first-answer latency improved substantially. The new risk is completion latency after first answer, where `general` and `sensitive` also show slower tails. The production trace points to synchronous suggestions as the most likely completed-latency driver: across eight copied trace summaries, `suggestions` had median `4124 ms`, p95 `7213 ms`, and was the top phase in five of eight runs. The slowest explicit-recall timeout run spent `6977 ms` in `suggestions` after the main answer had already started and finished.

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

Status: implemented, committed, deployed, production-benchmarked, and production-trace-validated on 2026-07-19. Local gate evidence: `pytest tests/backend/test_config.py tests/backend/test_conversation_context_service.py tests/backend/test_orchestration_service.py tests/backend/test_turn_latency_trace.py tests/backend/test_memory_query_tool.py tests/backend/test_memory_policy.py -q` produced `41 passed, 2 skipped`. Production memory-specific gate passed: explicit-recall long-term memory was bounded by timeout. Broader completed-latency gate is still partial because suggestions dominated several slow completed traces.

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

Local implementation gate passed on 2026-07-19 with `41 passed, 2 skipped`. Live production benchmark after deployment was written to `docs/worklog/202607/2026_07_19_experiment/production_latency_memory_timeout_20260719_072029.json` and summarized in `docs/worklog/202607/2026_07_19_experiment/production_latency_memory_timeout_20260719_072029.md`. Client-visible first-answer latency improved versus the prior 20-run trace-enabled run:

- Overall first-content median: `3289.88 ms` to `3131.11 ms`.
- Overall first-content p95: `7237.36 ms` to `5989.32 ms`.
- Explicit-recall first-content median: `7117.75 ms` to `5356.67 ms`.
- Explicit-recall completed median: `8548.30 ms` to `7961.18 ms`.

Production server-side trace confirmation was added from `temp/log.md` for the same benchmark window. The memory-specific gate passed:

- Explicit-recall timeout run `latency-benchmark-1784445736527`: `memory_query:timeout`, `long_term_memory=2049 ms`, `prompt_assembly=2572 ms`, `time_to_first_answer_ms=4452`.
- Explicit-recall timeout run `latency-benchmark-1784445765402`: `memory_query:timeout`, `long_term_memory=2000 ms`, `prompt_assembly=2524 ms`, `time_to_first_answer_ms=4202`.
- Previous slow explicit-recall traces had `long_term_memory=3914 ms` to `4127 ms` and `prompt_assembly=4439 ms` to `4647 ms`.

The broader completed-latency gate remains partial because overall completed median regressed from `5421.39 ms` to `7251.20 ms`. The same production trace window shows the completed-latency regression is most likely suggestion-driven: copied trace summaries had `suggestions` median `4124 ms`, p95 `7213 ms`, and `top_phase:suggestions` in the slow completed traces.

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

### Phase 4A: Profile Long-Term Memory Retrieval Efficiency

Status: implemented locally and partially production-verified on 2026-07-19. Local gate evidence: `phase4a_gate_output.txt` recorded `16 passed, 4 warnings` for trace/context tests and `17 passed` for memory-policy/runtime tests; `phase4a_memory_regression_output.txt` recorded `43 passed` for memory regression coverage. Production profiling evidence exists but is under-sampled: the copied complete backend log contains `2` memory retrieval summaries, both timed out around the `2000 ms` foreground memory budget. Completed sub-step medians across those two samples were approximately `working_memory=1143 ms`, `cold_memory_zpd_query=751 ms`, and `cold_memory_learner_state=175 ms`. Phase 4A is experiment-only: it adds measurement, runs controlled benchmarks, and produces a report. It must not make retrieval-speed optimizations beyond instrumentation.

#### Problem

Phase 3 added a guardrail: explicit-recall memory no longer blocks the main answer beyond the configured timeout. That protects user-visible response speed, but it may simply fail fast. The deployed trace showed `memory_query:timeout` for explicit-recall runs, which means the system did not successfully retrieve long-term memory inside the foreground budget.

The current trace only measures `long_term_memory` as one phase. It does not show whether time is spent in working memory, cold memory, embedding, intent labeling, STITCH label filtering, vector search, reranking, result formatting, network/database calls, or GUM background contention. Without sub-step attribution, a fixed `2000 ms` timeout is too blunt: it protects latency but cannot improve successful recall quality.

#### Assumptions

Explicit recall remains a foreground product capability. The target is not to remove long-term memory or shorten the timeout blindly. The target is to make successful long-term memory retrieval complete faster and more predictably within the current timeout budget.

Memory quality and speed must both be measured. A lower timeout is not a success if recall success rate drops. This phase must track timeout rate, successful recall rate, empty-result rate, cache-hit rate, and sub-step latency. Logs must remain privacy-safe and must not include raw user text, memory content, prompts, model output, credentials, or sensitive labels.

#### Solution

Add sub-step tracing inside the long-term memory retrieval path and run a controlled memory-focused experiment. The implementation should expose safe internal timings for `MemoryQueryTool.execute()` and its downstream GUM/cold/working memory calls. Phase 4A should identify whether the dominant cost is query normalization, working memory, cold memory, embedding, intent labeling, STITCH filtering, vector search, reranking, result formatting, network/database calls, or GUM background contention.

This phase should keep the Phase 3 timeout in place as a guardrail while making the underlying retrieval path measurable. The success criterion is not lower latency yet; success means every explicit-recall run has enough attribution to choose a Phase 4B optimization safely.

The experiment report should recommend SLO targets for Phase 4B. A reasonable starting point to evaluate is: memory retrieval p50 below `500 ms`, p95 below `1500 ms`, timeout rate below `5%` for explicit recall, and no regression in safe fallback behavior.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed public module, class, and function. Document memory sub-step trace semantics, retrieval success/failure definitions, timeout interaction with Phase 3, cache-key privacy, and memory quality metrics. Inline comments should explain only non-obvious retrieval short-circuits, cache invalidation, and privacy boundaries. Structured logs must include `run_id` or `conversation_id`, route, memory outcome, sub-step durations, cache status, timeout status, result count bucket, and safe fallback reason, while excluding raw user text, prompts, memory contents, model output, credentials, and sensitive labels.

Modify `backend/tools/memory_query.py` and downstream memory integration boundaries to emit safe sub-step timings. If the existing tool already queries working and cold memory concurrently, preserve that behavior and measure each branch separately. Add a small internal trace object if `TurnLatencyTrace` is too orchestration-focused.

Modify `backend/services/conversation_context_service.py` to propagate the memory sub-step trace outcome into `TurnLatencyTrace` or structured logs. Keep the Phase 3 timeout/cache behavior intact.

Modify `scripts/performance/benchmark_chat_latency.py` or add a memory-focused benchmark script if needed to run repeated explicit-recall scenarios with stable prompts and capture memory outcome distribution. The script should report timeout rate, cache-hit rate, success/empty result counts, and memory sub-step latency percentiles.

Add or update `docs/worklog/202607/2026_07_19_experiment/memory_retrieval_efficiency_report.md` with the experiment setup, raw artifact links, sub-step distribution, timeout rate, recall-success proxy, and recommended Phase 4B optimization target.

Do not change SSE wire format in this phase.

#### Expected File Tree After Phase 4A

Cumulative tree after Phase 4A:

```text
backend/
├── services/
│   ├── conversation_context_service.py  [modified]
│   ├── memory_query.py                  [modified]
│   ├── memory_retrieval_trace.py        [new if trace is extracted]
│   └── turn_latency_trace.py            [modified if memory summary changes]
scripts/
└── performance/
    └── benchmark_memory_retrieval.py    [new if dedicated benchmark is needed]
docs/
└── worklog/
    └── 202607/
        └── 2026_07_19_experiment/
            └── memory_retrieval_efficiency_report.md [new]
tests/
└── backend/
    ├── test_conversation_context_service.py [modified]
    ├── test_memory_query_tool.py        [modified]
    ├── test_memory_retrieval_trace.py   [new if trace is extracted]
    └── test_turn_latency_trace.py       [modified if memory summary changes]
```

#### Work List

1. [x] Modify `MemoryQueryTool.execute()` in `backend/tools/memory_query.py`.
   - [x] Add safe sub-step timing for working memory lookup.
   - [x] Add safe sub-step timing for cold memory lookup.
   - [x] Add safe sub-step timing around learner-state lookup, ZPD query generation, embedding, vector search, BM25 search, RRF fusion, document fetch, and result formatting when those boundaries are locally observable.
   - [x] Emit one privacy-safe memory retrieval summary with outcome, elapsed milliseconds, result count bucket, timeout status, and cache status.
2. [x] Add proposed `MemoryRetrievalTrace` in `backend/services/memory_retrieval_trace.py`.
   - [x] Add stable sub-step names and elapsed timing snapshots.
   - [x] Add result outcome fields such as `retrieved`, `empty`, `timeout`, `error`, and `cache_hit`.
   - [x] Exclude raw query text and memory content from snapshots.
3. [x] Modify `ConversationContextService._query_long_term_memory()` in `backend/services/conversation_context_service.py`.
   - [x] Preserve Phase 3 timeout/cache behavior.
   - [x] Attach memory retrieval sub-step summaries to the existing trace/log path.
   - [x] Keep timeout fallback honest and unchanged.
4. [x] Add or extend performance tooling.
   - [x] Add proposed `scripts/performance/benchmark_memory_retrieval.py` to report memory timeout rate, success rate, empty-result rate, cache-hit rate, and sub-step latency percentiles from backend logs.
5. [x] Add `docs/worklog/202607/2026_07_19_experiment/memory_retrieval_efficiency_report.md`.
   - [x] Record experiment setup, prompt set, environment, and commands.
   - [ ] Record production memory sub-step latency distribution and timeout/cache/success/empty rates after deployment.
   - [ ] Name one recommended Phase 4B bottleneck target after production profiling.
6. [x] Add or extend tests.
   - [x] `tests/backend/test_memory_query_tool.py`: assert sub-step trace fields are emitted without raw user text or memory content.
   - [x] `tests/backend/test_conversation_context_service.py`: assert Phase 3 timeout fallback remains unchanged after memory tracing.
   - [x] `tests/backend/test_memory_retrieval_trace.py`: assert trace snapshot timing, outcome, and privacy.
   - [x] `tests/backend/test_turn_latency_trace.py`: existing trace summary tests continue to pass.

#### Test Plan

Use mocked memory dependencies to validate sub-step trace emission, privacy, timeout behavior, cache behavior, empty-result handling, and fast-path correctness. Do not use live memory stores in unit tests. Use production-like live validation only after the focused unit gate passes.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_memory_query_tool.py tests/backend/test_conversation_context_service.py tests/backend/test_turn_latency_trace.py -q
PYTHONPATH=. pytest tests/backend/test_memory_policy.py tests/backend/test_runtime_contracts.py -q
```

Add `PYTHONPATH=. pytest tests/backend/test_memory_retrieval_trace.py -q` if `backend/services/memory_retrieval_trace.py` is extracted.

#### Expected Output / Result

Long-term memory retrieval becomes measurable at the sub-step level. The experiment report identifies the highest-confidence bottleneck and recommends a Phase 4B optimization. The Phase 3 timeout remains as a safety boundary and is not weakened.

#### Testing Script

##### Act 01: Trace Memory Sub-Steps

Run an explicit-recall memory query with mocked working and cold memory branches.

Pass condition: the memory retrieval trace records safe sub-step durations and does not include raw user text or memory content.

##### Act 02: Preserve Timeout Fallback

Mock a long-term memory query that exceeds the Phase 3 timeout.

Pass condition: the prompt still uses the honest timeout fallback, `memory_query:timeout` is recorded, and the stream can continue.

##### Act 03: Produce Memory Retrieval Report

Run the memory-focused benchmark and collect backend trace logs.

Pass condition: `memory_retrieval_efficiency_report.md` records sub-step p50/p95, timeout rate, cache-hit rate, empty-result rate, and a recommended Phase 4B target.

##### Act 04: Production Memory Retrieval Benchmark

Run a 20-run live explicit-recall benchmark after deployment and collect backend trace logs.

Pass condition: memory timeout rate, successful recall rate, and `long_term_memory` p50/p95 are recorded and compared against the Phase 3 production trace window.

#### Gate to Enter the Next Phase

The next phase must not start until these commands pass:

```bash
PYTHONPATH=. pytest tests/backend/test_memory_query_tool.py tests/backend/test_conversation_context_service.py tests/backend/test_memory_policy.py tests/backend/test_turn_latency_trace.py -q
python scripts/performance/benchmark_chat_latency.py --mode live --runs 20 --warmup 2 --output docs/worklog/202607/2026_07_19_experiment/production_latency_memory_efficiency.json
```

Retain evidence showing memory sub-step attribution, timeout rate, cache-hit rate, empty-result rate, and successful recall proxy. The phase passes only if the report identifies a concrete Phase 4B target or explicitly states why the result is inconclusive and what extra instrumentation or samples are required. Do not lower the timeout as a substitute for retrieval efficiency.

Current production profiling result: two deployed summary events prove the instrumentation works, but the sample is still insufficient for Phase 4B target selection. Because Phase 4B is now suspended by product prioritization, the next active latency work should target suggestion completion latency. If Phase 4B is resumed later, collect an explicit-recall-heavy benchmark to produce enough samples for p50/p95 sub-step attribution.

#### Phase Commit

Commit message:

```text
feat(backend): profile long-term memory retrieval
```

Stage only Phase 4A files and hunks:

```text
backend/services/conversation_context_service.py
backend/tools/memory_query.py
backend/services/memory_retrieval_trace.py
backend/services/turn_latency_trace.py
backend/tools/registry.py
backend/gum_integration.py
backend/cold_memory.py
scripts/performance/benchmark_chat_latency.py
scripts/performance/benchmark_memory_retrieval.py
docs/worklog/202607/2026_07_19_experiment/memory_retrieval_efficiency_report.md
tests/backend/test_conversation_context_service.py
tests/backend/test_memory_query_tool.py
tests/backend/test_memory_retrieval_trace.py
tests/backend/test_turn_latency_trace.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): profile long-term memory retrieval"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 4B: Optimize Measured Long-Term Memory Bottleneck

Status: suspended on 2026-07-19 by product prioritization. Phase 4A instrumentation is implemented and partially production-verified, but the current production log and user feedback indicate that explicit-recall first-answer latency is acceptable enough to defer deeper long-term-memory retrieval optimization. This phase should remain in the plan as a future retrieval-quality/efficiency track, but it is not the next implementation priority.

Do not start Phase 4B unless product feedback changes or production traces show explicit-recall first-answer latency has again become the dominant user-visible problem. The next active implementation phase is Phase 5, which targets the final post-answer wait caused by synchronous suggestion generation.

#### Problem

Phase 4A is expected to reveal where long-term memory retrieval spends time. The currently available production evidence is useful but under-sampled; likely fixes such as embedding cache, intent-label cache, STITCH short-circuiting, candidate caps, or vector index tuning are still hypotheses. Implementing several at once would make the result hard to attribute and could degrade recall quality while appearing faster.

The product problem remains that explicit recall should usually retrieve useful memory within the foreground budget. Phase 3 protects the answer when retrieval is slow, but if Phase 4A shows a high timeout rate or expensive sub-step, users still lose personalization on recall questions.

#### Assumptions

Phase 4A must produce enough evidence to rank at least one dominant bottleneck before this suspended phase can resume. If Phase 4A remains inconclusive, Phase 4B must not guess; it should first add the missing instrumentation or samples as a small follow-up to Phase 4A.

Only one primary optimization should be implemented in Phase 4B unless the Phase 4A report proves two changes are tightly coupled. Memory quality is part of the gate: lower latency is not sufficient if successful recall rate drops, empty-result rate rises unexpectedly, or timeout fallback becomes misleading.

#### Solution

Implement the smallest targeted optimization that addresses the Phase 4A top bottleneck. Examples:

- If embedding or intent labeling dominates, add a bounded hashed cache for normalized explicit-recall queries.
- If STITCH filtering or rerank dominates, add zero/one-candidate short-circuits and measured candidate-count limits.
- If cold memory dominates network/database time, tune the query shape, index path, or concurrent branch behavior.
- If result formatting dominates, reduce redundant transformations and avoid repeated serialization work.
- If working memory already satisfies recall with high confidence, return it early while optionally letting cold memory become a non-blocking enrichment path in a later phase.

The optimization must keep Phase 3 timeout/cache behavior in place. It should make timeout less frequent, not hide timeouts.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed public module, class, and function. Document the Phase 4A evidence that justifies the selected optimization, the cache/short-circuit/index invariants, recall-quality risk, and rollback behavior. Inline comments should explain why the selected optimization is safe for memory quality and privacy. Structured logs must include `run_id` or `conversation_id`, selected optimization outcome, cache/short-circuit status, elapsed milliseconds, result count bucket, and safe fallback reason, while excluding raw user text, prompts, memory contents, model output, credentials, and sensitive labels.

Modify only the files required by the selected Phase 4A bottleneck. If a cache is added, prefer a bounded TTL cache with hashed keys and no raw text in logs. If a short-circuit is added, preserve the previous result shape and add tests proving zero/one-candidate and multi-candidate behavior. If a query/index path is changed, keep compatibility with existing memory records and incomplete provenance.

Update `scripts/performance/benchmark_memory_retrieval.py` or the selected benchmark command to compare before/after results using the same prompt set from Phase 4A. Update `memory_retrieval_efficiency_report.md` with the Phase 4B result table and conclusion.

Do not change SSE wire format in this phase.

#### Expected File Tree After Phase 4B

Cumulative tree after Phase 4B:

```text
backend/
├── services/
│   ├── conversation_context_service.py  [modified if selected bottleneck requires it]
│   ├── memory_query.py                  [modified if selected bottleneck requires it]
│   ├── memory_retrieval_trace.py        [modified if trace outcome changes]
│   └── explicit_memory_cache.py         [modified if cache behavior changes]
scripts/
└── performance/
    └── benchmark_memory_retrieval.py    [modified if dedicated benchmark exists]
docs/
└── worklog/
    └── 202607/
        └── 2026_07_19_experiment/
            └── memory_retrieval_efficiency_report.md [modified]
tests/
└── backend/
    ├── test_conversation_context_service.py [modified if context behavior changes]
    ├── test_memory_query_tool.py        [modified]
    ├── test_memory_retrieval_trace.py   [modified if trace outcome changes]
    └── test_explicit_memory_cache.py    [new if cache behavior is expanded]
```

#### Work List

1. [ ] Read `docs/worklog/202607/2026_07_19_experiment/memory_retrieval_efficiency_report.md`.
   - [ ] Select exactly one primary bottleneck target for Phase 4B.
   - [ ] Record the chosen target and expected mechanism in the report before editing code.
2. [ ] Modify the selected memory retrieval file.
   - [ ] If the bottleneck is in `MemoryQueryTool.execute()` in `backend/tools/memory_query.py`, add the selected cache, fast path, or query-shape change there.
   - [ ] If the bottleneck is in `ConversationContextService._query_long_term_memory()` in `backend/services/conversation_context_service.py`, add only the required orchestration-level change there.
   - [ ] If the bottleneck is in cache behavior, modify `backend/services/explicit_memory_cache.py` or add a clearly scoped new helper.
3. [ ] Preserve observability.
   - [ ] Update `backend/services/memory_retrieval_trace.py` or existing trace fields if the optimization adds a new safe outcome.
   - [ ] Ensure production logs can distinguish cache hit, short-circuit, optimized query path, timeout, empty result, and retrieved result.
4. [ ] Extend tests.
   - [ ] `tests/backend/test_memory_query_tool.py`: assert optimized path preserves result shape and avoids the measured expensive call when eligible.
   - [ ] `tests/backend/test_conversation_context_service.py`: assert timeout fallback and honest prompt state remain unchanged.
   - [ ] `tests/backend/test_explicit_memory_cache.py`: assert TTL/privacy behavior if cache behavior changes.
   - [ ] `tests/backend/test_memory_retrieval_trace.py`: assert new optimization outcome is privacy-safe if trace changes.
5. [ ] Update experiment evidence.
   - [ ] Re-run the same benchmark prompt set used in Phase 4A.
   - [ ] Update `memory_retrieval_efficiency_report.md` with before/after p50, p95, timeout rate, success/empty rate, cache-hit rate, and conclusion.

#### Test Plan

Use mocked tests for the selected optimization and a repeated benchmark for the same explicit-recall prompt set from Phase 4A. The test plan must cover success, timeout, empty result, cache/short-circuit eligibility, and non-eligibility. Do not use live memory stores in unit tests.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_memory_query_tool.py tests/backend/test_conversation_context_service.py tests/backend/test_memory_policy.py -q
PYTHONPATH=. pytest tests/backend/test_turn_latency_trace.py tests/backend/test_runtime_contracts.py -q
python scripts/performance/benchmark_memory_retrieval.py --runs 20 --output docs/worklog/202607/2026_07_19_experiment/production_latency_memory_efficiency_optimized.json
```

If no dedicated memory benchmark exists, use the equivalent `benchmark_chat_latency.py` live explicit-recall subset and document the limitation in the report.

#### Expected Output / Result

The selected memory retrieval bottleneck improves in the same benchmark shape used by Phase 4A. Explicit-recall timeout rate should decrease, `long_term_memory` p95 should decrease, and successful recall or non-empty result rate should not regress. Logs remain privacy-safe and keep Phase 3 timeout behavior visible.

#### Testing Script

##### Act 01: Selected Optimization Is Used

Run the eligible mocked memory query identified by Phase 4A.

Pass condition: the optimized path is recorded and the expensive mocked sub-step is skipped or reduced.

##### Act 02: Non-Eligible Query Uses Normal Path

Run a mocked memory query that should not use the optimization.

Pass condition: the normal path still executes and returns the same result shape as before.

##### Act 03: Timeout Fallback Remains Honest

Force the optimized path and downstream memory query to exceed the Phase 3 timeout.

Pass condition: `memory_query:timeout` is recorded and the prompt does not claim successful long-term recall.

##### Act 04: Before/After Benchmark Comparison

Run the same explicit-recall benchmark prompt set from Phase 4A after deployment.

Pass condition: the report shows before/after memory p50, p95, timeout rate, and recall-success proxy with no privacy-sensitive log content.

#### Gate to Resume This Phase

This suspended phase must not resume until these commands pass:

```bash
PYTHONPATH=. pytest tests/backend/test_memory_query_tool.py tests/backend/test_conversation_context_service.py tests/backend/test_memory_policy.py tests/backend/test_turn_latency_trace.py -q
python scripts/performance/benchmark_memory_retrieval.py --runs 20 --output docs/worklog/202607/2026_07_19_experiment/production_latency_memory_efficiency_optimized.json
```

Retain the updated experiment report and benchmark artifacts. The phase passes only if the selected bottleneck improves and memory quality proxy does not regress. If the optimization fails, revert or disable only the Phase 4B optimization path and keep Phase 4A instrumentation.

#### Phase Commit

Commit message:

```text
feat(backend): optimize measured memory retrieval bottleneck
```

Stage only Phase 4B files and hunks selected by the Phase 4A report:

```text
backend/services/conversation_context_service.py
backend/tools/memory_query.py
backend/services/memory_retrieval_trace.py
backend/services/explicit_memory_cache.py
scripts/performance/benchmark_memory_retrieval.py
docs/worklog/202607/2026_07_19_experiment/memory_retrieval_efficiency_report.md
tests/backend/test_conversation_context_service.py
tests/backend/test_memory_query_tool.py
tests/backend/test_memory_retrieval_trace.py
tests/backend/test_explicit_memory_cache.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): optimize measured memory retrieval bottleneck"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 5: Bound Suggestion Tail And Reduce Provider First-Token Latency

Status: partially implemented locally on 2026-07-19. The first Phase 5 patch bounded foreground suggestion generation and removed the misleading `✨ 生成回答` status badge locally. Production validation then showed that suggestion latency is no longer the dominant issue in the copied trace: `suggestions=983 ms`, while `provider_first_token_ms=6269 ms`. Therefore the active Phase 5 target is now the main-model provider first-token wait, especially on `WEB_REQUIRED` turns.

#### Problem

In the Phase 3 production trace window, `suggestions` had median `4124 ms`, p95 `7213 ms`, and was the top phase in five of eight copied trace summaries. The first Phase 5 implementation bounded that tail. The latest copied production log changed the diagnosis: a `WEB_REQUIRED` turn recorded `suggestions=983 ms`, but `provider_first_token_ms=6269 ms`, `main_model=7144 ms`, `search_routing=4489 ms`, and `web_search=2866 ms`. The user-visible pause now happens after pre-answer status events and before the first answer token, so it is not a suggestion-tail problem.

The old `✨ 生成回答` badge made this worse by telling the user that answer generation had begun even though the system was still waiting for the provider's first streamed content. That badge should be removed or kept out of the foreground UX.

#### Assumptions

Suggestions must remain enabled and product-visible, but they are no longer the primary target after the timeout/fallback patch. Existing SSE semantics must remain compatible: answer deltas still stream, suggestion events appear when available within the timeout, a compatible `event: done` is emitted even on fallback, and exactly one terminal `[DONE]` is emitted.

Provider first-token latency cannot be fully controlled by application code because OpenRouter/Gemini queueing and provider prefill time are external. The system can still reduce it by avoiding unnecessary tool declarations, shrinking expensive web-context prompts, lowering answer token budgets where policy allows, and adding provider/model comparison telemetry. It is not acceptable to fake answer tokens, claim progress that has not happened, or remove required Web/search grounding for Web-required queries.

#### Solution

Keep the bounded foreground suggestion path already implemented. Then reduce the main-model first-token wait by addressing avoidable system-side contributors before blaming the provider:

1. Remove the misleading pre-token `生成回答` status badge so the UI does not show a false progress state while waiting for first token.
2. Send the `send_epistolary_letter` tool only when the current user request plausibly asks for avatar/letter scheduling. General answers should not pay tool-planning overhead.
3. Add prompt-size and request-shape telemetry around the main model call: message count, approximate prompt characters, web-context result count, attachment parser flag, tool-enabled flag, max token budget, and provider first-token latency.
4. For `WEB_REQUIRED` turns, cap or summarize web context before the main model call if traces show large prompt size correlates with slow first token.
5. If provider first-token p95 remains high after request-shape reductions, run a model/provider comparison under the same prompt set before changing the production model.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed public module, class, and function. Document suggestion timeout semantics, fallback behavior, cache-key privacy, SSE compatibility boundaries, and terminal-event ownership. Inline comments should explain only non-obvious fallback and event-ordering decisions. Structured logs must include `run_id` or `conversation_id`, suggestion outcome, timeout/cache status, elapsed milliseconds, and safe fallback reason, while excluding raw user text, prompts, model output, suggestion text if unnecessary, credentials, and sensitive labels.

Modify `Settings` in `backend/config.py` to keep the suggestion latency control:

- `suggestion_generation_timeout_ms: int = 1000`.

Modify `PostTurnService.suggestion_events()` in `backend/services/post_turn_service.py` to apply the configured timeout around `SuggestionService.generate_suggestions()`. On success, emit the existing suggestion event shape. On timeout or unexpected failure, emit a compatible fallback event and proceed to terminal completion. The fallback must be deterministic, safe, and easy for clients to handle.

Modify `TurnLatencyTrace` only through existing milestone semantics. Existing `suggestions_started` and `suggestions_finished` marks remain stable; timeout uses `suggestions_timeout`, which is already compatible with phase-duration calculation.

Modify `OrchestrationService._node_post_generation()` in `backend/services/orchestration_service.py` to pass the configured timeout into post-turn suggestion handling. Do not change answer streaming or terminal SSE ownership.

Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py` to remove the pre-token `生成回答` status event. The first visible answer should come from the provider stream itself.

Modify `ConversationStreamService.stream()` in `backend/services/conversation_stream_service.py` to make tool attachment conditional. Add a small deterministic helper, proposed `should_enable_letter_tool(last_user_msg: str) -> bool`, that returns true only for likely letter/avatar scheduling requests. When false, omit `tools` and `tool_choice` from the provider request instead of sending an always-available tool.

Add safe request-shape logging in `ConversationStreamService.stream()` before the provider call. The event should be `orchestration.main_model_request_shape` and include `conversation_id`, `model`, `message_count`, `prompt_chars_bucket`, `web_context_result_count_bucket` if available, `tools_enabled`, `max_tokens`, `force_think`, and `attachment_parser`. Do not log raw message text, prompt text, web snippets, model output, credentials, or user identifiers beyond existing safe correlation IDs.

#### Expected File Tree After Phase 5

Cumulative tree after Phase 5:

```text
backend/
├── config.py                            [modified]
├── services/
│   ├── orchestration_service.py         [modified]
│   ├── conversation_stream_service.py   [modified]
│   └── post_turn_service.py             [modified]
tests/
└── backend/
    ├── test_config.py                   [modified]
    ├── test_conversation_stream_service.py [new if no focused stream-service test exists]
    ├── test_orchestration_service.py    [modified]
    └── test_post_turn_service.py        [modified]
```

#### Work List

1. [x] Modify `Settings` in `backend/config.py`.
   - [x] Add `suggestion_generation_timeout_ms`.
2. [x] Modify `PostTurnService.suggestion_events()` in `backend/services/post_turn_service.py`.
   - [x] Wrap `SuggestionService.generate_suggestions()` in a timeout using the configured value.
   - [x] Emit existing suggestion event shape on normal success.
   - [x] Emit a compatible empty `event: done` payload on timeout or unexpected failure.
   - [x] Record safe structured log `orchestration.suggestions_timeout`.
   - [x] Preserve terminal completion behavior and avoid duplicate `[DONE]`.
3. [x] Modify `OrchestrationService._node_post_generation()` in `backend/services/orchestration_service.py`.
   - [x] Pass suggestion timeout settings into `PostTurnService.suggestion_events()`.
   - [x] Preserve current answer stream ordering and SSE terminal ownership.
4. [x] Modify `OrchestrationService.execute()` in `backend/services/orchestration_service.py`.
   - [x] Remove the misleading pre-token `生成回答` status event.
   - [x] Preserve prompt assembly, main stream, post-generation, and terminal `[DONE]` ordering.
5. [ ] Modify `ConversationStreamService.stream()` in `backend/services/conversation_stream_service.py`.
   - [ ] Add proposed helper `should_enable_letter_tool(last_user_msg: str) -> bool`.
   - [ ] Omit `tools` and `tool_choice` for normal chat turns that are not likely letter/avatar scheduling requests.
   - [ ] Preserve `send_epistolary_letter` tool execution for eligible letter/avatar requests.
   - [ ] Add privacy-safe `orchestration.main_model_request_shape` logging.
6. [ ] Add or extend tests.
   - [x] `tests/backend/test_config.py`: assert suggestion timeout default and env override.
   - [x] `tests/backend/test_post_turn_service.py`: assert slow suggestions time out and still emit compatible events.
   - [x] Existing `tests/backend/test_orchestration_service.py` and `tests/backend/test_stream_endpoint.py`: preserve stream completion compatibility after removing `生成回答`.
   - [ ] `tests/backend/test_conversation_stream_service.py`: assert normal chat omits tools/tool_choice.
   - [ ] `tests/backend/test_conversation_stream_service.py`: assert letter/avatar request includes `send_epistolary_letter`.
   - [ ] `tests/backend/test_conversation_stream_service.py`: assert request-shape logs are privacy-safe.

#### Test Plan

Use mocked `SuggestionService.generate_suggestions()` calls to validate success, timeout, and failure behavior. Use mocked provider clients to validate conditional tool request shape and first-token telemetry without live provider calls. Existing accumulator and done-event tests must continue to pass because the user-facing SSE contract is the highest-risk compatibility boundary.

Commands:

```bash
PYTHONPATH=. pytest tests/backend/test_config.py tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py -q
PYTHONPATH=. pytest tests/backend/test_conversation_stream_service.py tests/backend/test_runtime_contracts.py tests/backend/test_stream_endpoint.py -q
```

#### Expected Output / Result

Suggestions remain enabled when they return within the configured budget, but they no longer block terminal completion beyond `suggestion_generation_timeout_ms`. Slow suggestions produce a compatible empty fallback and structured telemetry. The misleading `生成回答` badge is removed. Normal chat turns no longer send unnecessary tool definitions to the main model. Production traces should show request-shape metadata for first-token analysis, and provider first-token p95 should improve if tool-planning overhead was a contributor.

#### Testing Script

##### Act 01: Suggestions Return Quickly

Mock `SuggestionService.generate_suggestions()` to return before the timeout.

Pass condition: `PostTurnService.suggestion_events()` emits the existing suggestion event shape and no timeout log is emitted.

##### Act 02: Suggestions Time Out

Mock `SuggestionService.generate_suggestions()` to sleep longer than `suggestion_generation_timeout_ms`.

Pass condition: a compatible fallback event is emitted, `orchestration.suggestions_timeout` is logged once with safe metadata, and terminal completion proceeds.

##### Act 03: SSE Completion Remains Compatible

Run the stream endpoint or orchestration path with a slow mocked suggestion service.

Pass condition: answer deltas stream normally, suggestion fallback is compatible, and exactly one terminal `[DONE]` is emitted.

##### Act 04: Normal Chat Omits Tools

Run `ConversationStreamService.stream()` with a normal user question and a mocked provider client.

Pass condition: the provider request does not include `tools` or `tool_choice`.

##### Act 05: Letter Request Keeps Tool

Run `ConversationStreamService.stream()` with a request that clearly asks to send or schedule an avatar letter.

Pass condition: the provider request includes the `send_epistolary_letter` tool and keeps tool-call handling compatible.

##### Act 06: Request-Shape Telemetry Is Safe

Run a mocked stream with long prompt content and capture logs.

Pass condition: `orchestration.main_model_request_shape` is emitted with bucketed/safe fields and no raw prompt, user text, web snippet, model output, token, or credential content.

#### Gate to Enter the Next Phase

This is the final implementation phase gate before cross-phase acceptance:

```bash
PYTHONPATH=. pytest tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py tests/backend/test_chat_latency_benchmark.py -q
PYTHONPATH=. pytest tests/backend/test_config.py tests/backend/test_conversation_stream_service.py tests/backend/test_runtime_contracts.py tests/backend/test_stream_endpoint.py -q
python scripts/performance/benchmark_chat_latency.py --mode live --runs 20 --warmup 2 --output docs/worklog/202607/2026_07_19_experiment/production_latency_suggestion_timeout.json
```

Retain evidence showing suggestion timeout behavior, SSE compatibility, provider request-shape telemetry, and production trace outcomes. The phase passes only if copied production `turn_trace_summary` logs show `suggestions` no longer dominates completed latency past the configured timeout budget and `provider_first_token_ms` can be correlated with request shape. If provider first-token latency remains high after normal turns omit tools, the next step is a provider/model comparison rather than more local pipeline work.

#### Phase Commit

Commit message:

```text
feat(backend): bound foreground suggestion latency
```

Stage only Phase 5 files and hunks:

```text
backend/config.py
backend/services/orchestration_service.py
backend/services/conversation_stream_service.py
backend/services/post_turn_service.py
tests/backend/test_config.py
tests/backend/test_conversation_stream_service.py
tests/backend/test_orchestration_service.py
tests/backend/test_post_turn_service.py
```

Inspect `git status --short`, preserve unrelated user changes, stage only phase-owned paths or hunks, then run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "feat(backend): bound foreground suggestion latency"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Cross-Phase Regression and Final Acceptance

Run the full focused regression suite after all phase commits:

```bash
PYTHONPATH=. pytest tests/backend/test_turn_latency_trace.py tests/backend/test_turn_plan_service.py tests/backend/test_turn_intake_service.py tests/backend/test_conversation_context_service.py tests/backend/test_post_turn_service.py tests/backend/test_orchestration_service.py tests/backend/test_runtime_contracts.py tests/backend/test_stream_endpoint.py tests/backend/test_agent_foundations.py tests/backend/test_memory_policy.py tests/backend/test_memory_query_tool.py tests/backend/test_web_search_tool.py tests/backend/test_chat_latency_benchmark.py -q
python scripts/performance/benchmark_chat_latency.py --mode mocked --runs 10 --warmup 2 --output /tmp/areqa-pipeline-improvement.json
```

If no separate `backend/services/explicit_memory_cache.py` or `backend/services/suggestion_cache.py` exists because the implementation stayed inside existing services, omit only that nonexistent file and document why.

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
- Production trace validates Phase 3 memory behavior: explicit-recall `long_term_memory` is bounded around the configured timeout instead of the pre-Phase-3 `3.9s` to `4.1s` range.
- Phase 4A production evidence shows long-term memory retrieval sub-step attribution and records that Phase 4B is suspended until explicit-recall first-answer latency becomes the dominant user-visible problem again.
- Phase 4B production evidence is required only if the suspended long-term-memory optimization phase is later resumed.
- Suggestions remain enabled and compatible, and Phase 5 bounds their foreground wait with timeout/fallback behavior.
- Production trace after Phase 5 should show `suggestions` no longer dominates completed latency past the configured suggestion timeout budget.
- `search_mode=never` still performs zero external search calls.
- `search_mode=auto` and Web-required queries still respect `SearchPolicy`/`TutorAgent` and `ToolBudgetTracker`.
- Greeting/static low-information behavior still short-circuits safely.
- SSE remains compatible: metadata/status/action events can appear early, answer deltas stream, suggestions/done remain valid, and exactly one terminal `data: [DONE]` is emitted.
- Structured logs are privacy-safe and contain safe reason codes, phase timings, route, model-call budget, and fallback outcomes.
- Mock benchmark shows expected TTFT and completion-time improvement; live benchmark provides production evidence before rollout.
- Production trace should show explicit-recall `long_term_memory` no longer blocks `time_to_first_answer_ms` past the configured fallback window, and synchronous suggestions no longer block terminal completion past the configured suggestion fallback window.

Remaining risks and mitigations:

- Memory recall completeness may drop on timeout. Mitigate by honest fallback copy, short-lived cache, and optional follow-up memory enrichment when late memory arrives.
- Disabling general foreground long-term memory may reduce personalization for some questions. Mitigate with explicit recall detection, hot-memory snapshots, and trace-backed rollout.
- Suggestion fallback quality may be lower than model-generated suggestions. Mitigate with conservative default suggestions, short TTL caching, timeout metrics, and a product review of fallback wording.
- Suggestion cache keys may accidentally include sensitive text if implemented carelessly. Mitigate with hashed/fingerprinted keys and tests asserting raw text is absent from logs/cache metadata.
- Later parallel foreground work can introduce task leaks or cancellation bugs. Mitigate with explicit task ownership tests and runtime-contract tests only if that later work is reintroduced.
- Model-call budgets can underfit future product requirements. Mitigate by making budgets configurable and logging budget exhaustion with safe reason codes.

Final repository checks:

```bash
git status --short
git log --oneline -6
```

The final status must show no planned implementation files left unstaged or uncommitted, except unrelated user changes that were intentionally preserved. The log must contain the phase commits in order:

```text
feat(backend): add chat turn latency tracing
feat(backend): add deterministic chat turn planning
feat(backend): bound explicit recall memory latency
feat(backend): profile long-term memory retrieval
feat(backend): optimize measured memory retrieval bottleneck
feat(backend): bound foreground suggestion latency
```

No phase may be considered complete without its gate evidence and phase commit.
