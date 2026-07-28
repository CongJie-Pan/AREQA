# Learning Manager Orchestrator Implementation Plan

This revised plan incorporates the audit feedback from `docs/tech_docs/pplx/PELICAN Learning Manager Orchestrator 計畫書審查.md`. The main correction is to move orchestration safety work earlier: model health checks, strict route contracts, confidence thresholds, immutable turn snapshots, idempotent same-turn tracing, legal route matrices, fallback equivalence tests, and no-mastery-write assertions are now phase gates rather than late documentation tasks. The six-stage PELICAN pipeline remains the learning guardrail and state owner; the new `LearningManagerOrchestrator` becomes the turn-level decision agent that interprets the current learner turn and selects which existing specialist capability should run.

### Phase 1: Model Routes, Health Check, and Structured Output Contract

#### Problem

The current learner-facing route defaults to `google/gemini-3.1-flash-lite`, but the requested production route is `google/gemini-3.5-flash-lite` from `docs/tech_docs/API_model_docs/Gemini_3.5_Flash_Lite_-_API_Pricing_&_Benchmarks_OpenRouter.md`. The original plan also deferred OpenRouter structured-output compatibility checks too late, which creates a risk that Phase 2 builds a JSON-schema orchestration path on a provider route that may not support the selected response format.

#### Assumptions

`google/gemini-3.5-flash-lite` is the correct OpenRouter slug because the local model document states that exact model. Orchestrator and learner-facing tutor routes should default to this model, but skill generation routes should stay category-specific. If a live health check cannot run because credentials are unavailable, the implementation must still be testable with fake health results and must fail closed to JSON-object prompting plus local validation.

#### Solution

Update tutor and orchestrator model resolution before building the orchestrator. Add a dedicated orchestrator route resolver and a structured-output health probe that can report whether strict JSON schema is supported, unsupported, unavailable, or unknown. The orchestrator implementation in later phases must consult this capability and use deterministic fallback when strict structured output is rejected.

#### Implementation

> Context: Add or update Google-style docstrings for every changed public module, class, and function in this phase. Document route precedence, why tutor/orchestrator routes are separate from skill generation, what the health probe does and does not prove, provider compatibility boundaries for OpenRouter, and privacy rules. Do not log raw learner text, prompts, model output, credentials, response bodies, or reasoning details. Use inline comments only at compatibility fallback decisions.

Modify `misc/PELICAN_mvp/pelican_mvp/llm.py` to set `DEFAULT_TUTOR_MODEL = "google/gemini-3.5-flash-lite"` and add `DEFAULT_ORCHESTRATOR_MODEL = "google/gemini-3.5-flash-lite"`. Add `LlmAdapter.orchestrator_model_route()` with precedence `PELICAN_ORCHESTRATOR_MODEL`, `PELICAN_TUTOR_MODEL`, `PELICAN_LLM_MODEL`, default. Add a proposed health result field or helper for orchestrator structured-output support, reusing the existing safe health style.

#### Expected File Tree After Phase 1

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      llm.py                                      [modified]
    tests/
      test_llm.py                                 [modified]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/llm.py`.
   - [ ] Change `DEFAULT_TUTOR_MODEL` to `google/gemini-3.5-flash-lite`.
   - [ ] Add the proposed `DEFAULT_ORCHESTRATOR_MODEL = "google/gemini-3.5-flash-lite"`.
   - [ ] Add the proposed `LlmAdapter.orchestrator_model_route()` method with the documented override precedence.
   - [ ] Add the proposed `LlmAdapter.check_orchestrator_structured_output_health()` helper or extend `check_route_health()` with a safe orchestrator schema probe.
   - [ ] Ensure health results include only safe reason codes, status, and provider error class/status.
2. [ ] Modify `misc/PELICAN_mvp/tests/test_llm.py`.
   - [ ] Add default tutor route assertions for `google/gemini-3.5-flash-lite`.
   - [ ] Add orchestrator route precedence assertions.
   - [ ] Add tests that skill generation defaults remain unchanged.
   - [ ] Add fake provider tests for strict schema supported, unsupported, unavailable, and unknown health states.

#### Test Plan

Use monkeypatched environment variables and fake OpenRouter/OpenAI-compatible client responses. Assert route precedence, health probe classification, safe failure metadata, and skill route isolation.

#### Expected Output / Result

Tutor and orchestrator routes default to `google/gemini-3.5-flash-lite`. The code can determine whether strict structured output is usable for orchestration and can expose that status safely before the orchestrator depends on it.

#### Testing Script

##### Act 01: Tutor Route Default

Clear `PELICAN_TUTOR_MODEL` and `PELICAN_LLM_MODEL`, instantiate `LlmAdapter`, and call `tutor_model_route()`.

Pass condition: the returned route is `google/gemini-3.5-flash-lite`.

##### Act 02: Orchestrator Route Precedence

Set `PELICAN_ORCHESTRATOR_MODEL=custom/orchestrator`, `PELICAN_TUTOR_MODEL=custom/tutor`, and `PELICAN_LLM_MODEL=custom/legacy`, then call `orchestrator_model_route()`.

Pass condition: the returned route is `custom/orchestrator`.

##### Act 03: Structured Output Health Fallback

Use a fake client that rejects strict `json_schema` response format for the orchestrator model.

Pass condition: the health helper returns an unsupported/compatibility failure status with safe reason codes and no provider body.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_llm.py`. The command must pass. Do not enter Phase 2 unless route precedence, skill isolation, and structured-output health classification are covered.

#### Phase Commit

Commit message: `feat(pelican): configure orchestrator model health`

Stage only `misc/PELICAN_mvp/pelican_mvp/llm.py` and `misc/PELICAN_mvp/tests/test_llm.py`. Inspect `git status --short`, preserve unrelated user changes, stage only these paths or exact hunks, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 2: Orchestrator Decision Schema, Route Matrix, and Immutable Snapshot

#### Problem

The current dialogue routing is rule-first and local to `DialogueActAgent`, so short learner turns can be misread as clarification or wrong evidence. The original plan also left the route enum broad and underspecified. That creates risks of silent misroutes, unclear confidence handling, and races between an orchestrator decision and mutable session state.

#### Assumptions

`LearningManagerOrchestrator` must not mutate `SessionState`. It may inspect raw learner text during interpretation, but safe metadata must exclude raw learner answers and model output. The engine must validate every route against the current phase before adopting it. A decision should be tied to an immutable turn snapshot with `turn_id`, `cycle_id`, phase, node id, prompt source, expected response shape, EDF labels, and recent safe signals.

#### Solution

Add a bounded orchestration contract with a strict route enum, confidence threshold policy, route legality matrix, immutable `LearningManagerTurnContext`, and deterministic fallback. The first implementation is structured orchestration, not a full autonomous tool-calling loop: one model call proposes a route, local validation checks the schema, confidence, phase legality, and snapshot identity, and the result becomes an accepted or fallback proposal.

#### Implementation

> Context: Add Google-style docstrings for the new module, public dataclasses, enums, validation helpers, and methods. Document the ownership invariant that the orchestrator proposes and the engine mutates. Document immutable snapshot fields, confidence thresholds, tiebreaker behavior, route legality, structured-output fallback, privacy boundaries, and structured logs. Add inline comments only where invalid model output is rejected, confidence ties are resolved, or route legality is enforced.

Create `misc/PELICAN_mvp/pelican_mvp/agents/learning_manager_orchestrator.py`. Add route and decision types in `models.py` only if they must be shared with engine traces or exports; otherwise keep them in the orchestrator module. Add `LlmAdapter.orchestrate_turn_decision()` using `orchestrator_model_route()` and the Phase 1 structured-output health signal. Add local validators for enum values, confidence range, confidence threshold, safe reason codes, target stage, and legal phase/route combinations.

#### Expected File Tree After Phase 2

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      agents/
        __init__.py                               [modified]
        learning_manager_orchestrator.py          [new]
      llm.py                                      [modified]
      models.py                                   [modified if shared types are needed]
    tests/
      test_learning_manager_orchestrator.py       [new]
      test_agent_contract.py                      [modified]
      test_llm.py                                 [modified]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/learning_manager_orchestrator.py`.
   - [ ] Add the proposed immutable `LearningManagerTurnContext` type.
   - [ ] Add the proposed `LearningManagerRoute` enum with fully documented routes: `diagnose_answer`, `clarify_current_prompt`, `interrupt_and_explain`, `resume_pipeline`, `continue_pipeline`, `fallback_legacy_pipeline`, and `reject_illegal_route`.
   - [ ] Add the proposed `LearningManagerDecision` type with route, target stage, confidence, reason code, proposal source, and snapshot id.
   - [ ] Add the proposed `LearningManagerRoutePolicy` or validation helper containing the legal phase/route matrix.
   - [ ] Add the proposed `LearningManagerOrchestrator.interpret_turn()` method.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/llm.py`.
   - [ ] Add the proposed `LlmAdapter.orchestrate_turn_decision()` method using `orchestrator_model_route()`.
   - [ ] Use strict JSON schema only when Phase 1 health allows it; otherwise use JSON-object prompting and local validation.
   - [ ] Validate payload shape, route enum, confidence bounds, reason code bounds, and target stage before returning a usable payload.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/agents/__init__.py`.
   - [ ] Export `LearningManagerOrchestrator` and public decision/context types.
4. [ ] Modify `misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`.
   - [ ] Test valid LLM route adoption for an answer attempt.
   - [ ] Test invalid route rejection into `fallback_legacy_pipeline` or `reject_illegal_route`.
   - [ ] Test low-confidence fallback using the documented threshold.
   - [ ] Test tie-breaking when two candidate routes have equal confidence.
   - [ ] Test unavailable LLM fallback.
   - [ ] Test immutable snapshot mismatch rejection.
   - [ ] Test raw learner text is not copied into safe metadata.
5. [ ] Modify `misc/PELICAN_mvp/tests/test_agent_contract.py`.
   - [ ] Add contract coverage that the orchestrator returns bounded proposal metadata and does not mutate state.
6. [ ] Modify `misc/PELICAN_mvp/tests/test_llm.py`.
   - [ ] Add orchestrator structured-output payload validation tests.

#### Test Plan

Use fake `LlmAdapter` objects and immutable context fixtures. Assert valid adoption, invalid fallback, low-confidence fallback, tiebreaker selection, snapshot mismatch rejection, route legality, safe reason codes, target stage constraints, and privacy boundaries.

#### Expected Output / Result

`LearningManagerOrchestrator` produces a bounded, phase-legal, confidence-gated decision for the current immutable turn snapshot. Invalid, low-confidence, stale, or provider-unavailable decisions fall back deterministically without mutating session state.

#### Testing Script

##### Act 01: Answer Attempt Adoption

Provide a fake LLM payload for a learner answer to the active tutor question with route `diagnose_answer` and confidence above the threshold.

Pass condition: `interpret_turn()` returns `diagnose_answer` with proposal source `llm`.

##### Act 02: Low Confidence Fallback

Provide a valid route payload with confidence below the threshold.

Pass condition: `interpret_turn()` returns `fallback_legacy_pipeline` with a low-confidence reason code.

##### Act 03: Illegal Route Rejection

Provide a payload that asks to run `diagnose_answer` during an onboarding-only context.

Pass condition: the decision is rejected or downgraded according to the route matrix and does not claim diagnosis is legal.

##### Act 04: Snapshot Privacy

Pass a learner answer containing distinctive raw text and inspect safe metadata.

Pass condition: the raw answer and model output do not appear in safe metadata.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py misc/PELICAN_mvp/tests/test_agent_contract.py misc/PELICAN_mvp/tests/test_llm.py`. Every focused test must pass. Do not enter Phase 3 if the route matrix, confidence policy, or stale-snapshot rejection is not tested.

#### Phase Commit

Commit message: `feat(pelican): add bounded learning orchestrator`

Stage only the new orchestrator module, related exports, shared model types if added, LLM orchestration helper, and focused tests. Inspect `git status --short`, preserve unrelated changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 3: Engine Wiring, Legal Dispatch, and Mastery-Write Protection

#### Problem

`PelicanEngine.respond()` currently routes by fixed phase first. The original plan did not define a strict enough engine-side contract for legal route dispatch, fallback equivalence, or protection against clarification turns accidentally writing mastery evidence. That is the highest-risk integration point because all state mutation still happens inside the engine.

#### Assumptions

The engine remains the only owner of session mutation, persistence, methodology events, learner progress, and mastery evidence. The orchestrator decision must be treated as a proposal that the engine validates against the same route matrix used in Phase 2. Legacy fixture behavior must remain equivalent when the orchestrator returns fallback. Onboarding should default to legacy handling unless an explicitly legal route is implemented and tested.

#### Solution

Instantiate `LearningManagerOrchestrator` in `PelicanEngine`, build an immutable context after `_begin_turn()`, and route through a narrow dispatcher. The dispatcher must validate snapshot identity, phase legality, idempotency key, and route confidence before calling existing specialist capabilities. Clarification and interruption routes must go through no-mastery-write paths. Fallback must delegate to the current legacy phase handler and be covered by behavioral equivalence tests.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed engine helper. Document legal dispatch, fallback equivalence, idempotency key use, same-turn event order, state ownership, mastery-write protection, and failure semantics. Use inline comments only where the engine rejects a route to preserve pipeline invariants or intentionally avoids mastery writes.

Modify `engine.py` to create `self.learning_manager_orchestrator`. Add helpers such as `_learning_manager_turn_context()`, `_legacy_phase_handler()`, `_validate_orchestrator_decision()`, `_route_orchestrated_turn()`, and `_assert_no_mastery_write_for_dialogue_route()` if useful. Record the orchestrator proposal before route execution, then record the applied route, then call the existing capability. Keep `_handle_diagnostic()`, `_handle_tutoring()`, and onboarding handlers reusable so fallback equivalence is testable.

#### Expected File Tree After Phase 3

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      engine.py                                  [modified]
      agents/
        __init__.py                              [modified if needed]
      models.py                                  [modified if route trace fields are shared]
    tests/
      test_engine.py                             [modified]
      test_pedagogical_flow.py                   [modified]
      test_chinese_history.py                    [modified]
      test_learning_manager_orchestrator.py      [modified if shared fixtures move]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py`.
   - [ ] Add `self.learning_manager_orchestrator = LearningManagerOrchestrator(self.llm)` in `PelicanEngine.__init__()`.
   - [ ] Add the proposed `PelicanEngine._learning_manager_turn_context()` helper that snapshots turn fields immutably.
   - [ ] Add the proposed `PelicanEngine._legacy_phase_handler()` helper for exact fallback delegation.
   - [ ] Add the proposed `PelicanEngine._validate_orchestrator_decision()` helper using the legal route matrix.
   - [ ] Add the proposed `PelicanEngine._route_orchestrated_turn()` helper.
   - [ ] Update `PelicanEngine.respond()` to call the orchestrator after `_begin_turn()` and before legacy phase handling.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py` route-specific paths.
   - [ ] Route `diagnose_answer` to the existing diagnosis path only when phase and node context are legal.
   - [ ] Route `clarify_current_prompt` and `interrupt_and_explain` to bounded tutoring/dialogue paths that do not update mastery evidence.
   - [ ] Route `resume_pipeline` and `continue_pipeline` only to legal continuation paths for the current phase.
   - [ ] Route illegal, stale, or low-confidence decisions to fallback with safe reason codes.
3. [ ] Modify `misc/PELICAN_mvp/tests/test_engine.py`.
   - [ ] Add fallback behavioral equivalence tests comparing output/state snapshots with and without fallback orchestration.
   - [ ] Add tests proving legacy onboarding still works and defaults to fallback unless a legal route is implemented.
   - [ ] Add tests asserting same-turn idempotency prevents duplicate route application.
4. [ ] Modify `misc/PELICAN_mvp/tests/test_pedagogical_flow.py`.
   - [ ] Add a generated humanities flow where a short learner answer is routed to diagnosis rather than clarification.
   - [ ] Add a clarification route test asserting no mastery evidence is written.
5. [ ] Modify `misc/PELICAN_mvp/tests/test_chinese_history.py`.
   - [ ] Add the regression where the tutor asks which Meiji reform most affected old class structures and the learner answers `廢藩置縣?`.
   - [ ] Add the regression where the learner asks `什麼轉折點?` and receives a focused clarification without replaying the whole lesson.

#### Test Plan

Use fake orchestrator decisions for deterministic engine routing. Assert route legality, current prompt behavior, knowledge updates, no-mastery-write clarification paths, fallback equivalence, idempotency, methodology event order, and safe structured logs.

#### Expected Output / Result

Learner turns are interpreted by `LearningManagerOrchestrator` before phase handlers. `廢藩置縣?` is treated as an answer attempt to the active question. `什麼轉折點?` is treated as a clarification request without mastery evidence. Fallback decisions preserve legacy behavior.

#### Testing Script

##### Act 01: Short Answer to Active Question

Set a generated humanities session where the current prompt asks which Meiji reform most affected old class structures. Submit `廢藩置縣?`.

Pass condition: the engine records route `diagnose_answer` and does not route the turn as term clarification.

##### Act 02: Concept Clarification

Set a generated humanities session where the previous tutor message mentions a turning point. Submit `什麼轉折點?`.

Pass condition: the engine returns a concise clarification response and does not record mastery evidence for the answer.

##### Act 03: Legacy Fallback Equivalence

Configure a fake orchestrator to return `fallback_legacy_pipeline` and run the same onboarding input through a pre-orchestrator-compatible path.

Pass condition: learner-visible output and relevant state snapshot fields are equivalent.

##### Act 04: Duplicate Route Guard

Attempt to apply the same orchestrator decision twice for one turn id.

Pass condition: the second application is ignored or rejected with a safe idempotency reason code.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_engine.py misc/PELICAN_mvp/tests/test_pedagogical_flow.py misc/PELICAN_mvp/tests/test_chinese_history.py misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`. All tests must pass. Do not enter Phase 4 if fallback equivalence, no-mastery-write clarification, route legality, and idempotency are not covered.

#### Phase Commit

Commit message: `feat(pelican): dispatch turns through orchestrator`

Stage only Phase 3 engine and test hunks. Inspect `git status --short`, preserve unrelated changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 4: Same-Turn Observability, Exports, and Documentation

#### Problem

An orchestration layer adds control complexity. Without same-turn trace ordering and safe observability, debugging can become harder than the previous fixed pipeline. The audit specifically calls out the need to correlate `decided`, `fallback`, and `route_applied` events in one turn and to avoid hidden memory overwrites or handoff ambiguity.

#### Assumptions

Existing observability should use `pelican_mvp.observability.log_event`. Logs and exports must never include raw learner text, prompts, model output, provider payloads, credentials, or reasoning details. Progress/demo exports may include bounded route labels only if they already expose methodology or proposal metadata.

#### Solution

Add same-turn structured logs and methodology trace entries for orchestrator decision, route validation, fallback, route application, specialist capability selection, and terminal tutor response. Include `turn_id`, `cycle_id`, route, target stage, proposal source, confidence bucket, reason code, and idempotency key. Update docs to explain pipeline versus orchestrator versus specialist capability ownership and model routing.

#### Implementation

> Context: Add Google-style docstrings for changed export or observability helpers. Document safe metadata fields, forbidden fields, event ordering, idempotency semantics, and failure handling. Add inline comments only where privacy redaction or event mapping is non-obvious.

Modify orchestrator and engine log call sites to emit stable events such as `pelican_learning_orchestrator_decided`, `pelican_learning_orchestrator_fallback`, `pelican_learning_orchestrator_route_applied`, and `pelican_learning_orchestrator_route_rejected`. Update export helpers only if they already surface agent proposal summaries. Add documentation under `misc/PELICAN_mvp/docs`.

#### Expected File Tree After Phase 4

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      engine.py                                  [modified]
      agents/
        learning_manager_orchestrator.py         [modified]
      progress.py                                [modified if exports need route labels]
    docs/
      learning_manager_orchestrator.md           [new]
    tests/
      test_learning_manager_orchestrator.py      [modified]
      test_engine.py                             [modified]
      test_e2e.py                                [modified]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/agents/learning_manager_orchestrator.py`.
   - [ ] Emit `pelican_learning_orchestrator_decided` for accepted decisions.
   - [ ] Emit `pelican_learning_orchestrator_fallback` for unavailable, invalid, low-confidence, stale, or unsupported structured-output decisions.
   - [ ] Include safe confidence bucket and reason code, not raw confidence rationale.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py`.
   - [ ] Emit `pelican_learning_orchestrator_route_applied` after validation and before specialist execution.
   - [ ] Emit `pelican_learning_orchestrator_route_rejected` for illegal route proposals.
   - [ ] Ensure same-turn events include `turn_id`, `cycle_id`, route, target stage, idempotency key, proposal source, and reason code.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/progress.py` only if current progress or demo export paths already expose agent proposal summaries.
   - [ ] Include bounded orchestrator route labels without raw learner text.
4. [ ] Create `misc/PELICAN_mvp/docs/learning_manager_orchestrator.md`.
   - [ ] Document pipeline versus orchestrator versus specialist capability ownership.
   - [ ] Document legal route matrix and fallback semantics.
   - [ ] Document model routing: orchestrator and learner-facing tutor default to `google/gemini-3.5-flash-lite`; skill generation remains category-routed.
   - [ ] Document structured-output health behavior and debugging logs.
5. [ ] Modify `misc/PELICAN_mvp/tests/test_e2e.py`.
   - [ ] Add end-to-end coverage that a generated humanities session records same-turn orchestrator events in order.
   - [ ] Assert event metadata is bounded and excludes raw learner text.

#### Test Plan

Run focused orchestrator, engine, and E2E tests. Capture log events using monkeypatching at the call site or the existing logging test pattern. Assert event names, event ordering, safe metadata, idempotency fields, route labels, fallback reasons, and absence of raw learner text.

#### Expected Output / Result

Developers can debug one learner turn from safe traces: orchestrator decision or fallback, route validation, route application, specialist capability execution, and tutor response are visible and correlated by `turn_id` and `cycle_id`.

#### Testing Script

##### Act 01: Accepted Route Trace

Run a generated humanities diagnostic turn with a fake accepted orchestrator decision.

Pass condition: logs include `pelican_learning_orchestrator_decided` before `pelican_learning_orchestrator_route_applied` with the same `turn_id` and `cycle_id`.

##### Act 02: Fallback Trace

Run a turn where the fake LLM returns an invalid or low-confidence route.

Pass condition: logs include `pelican_learning_orchestrator_fallback`, the engine completes the fallback route, and no raw learner text appears in the log metadata.

##### Act 03: Documentation Trace

Open the generated documentation and compare the described ownership model against the code paths.

Pass condition: the document names `LearningManagerOrchestrator`, the six-stage pipeline, specialist capabilities, the route matrix, Gemini 3.5 Flash Lite routing, health checks, and fallback behavior.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py misc/PELICAN_mvp/tests/test_engine.py misc/PELICAN_mvp/tests/test_e2e.py`. Then run `python -m pytest misc/PELICAN_mvp/tests` unless an unrelated pre-existing suite failure is documented before this phase. All orchestrator-related tests must pass and no privacy assertion may be weakened.

#### Phase Commit

Commit message: `docs(pelican): document orchestrator traces`

Stage only Phase 4 observability, export, documentation, and test hunks. Inspect `git status --short`, preserve unrelated changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Cross-Phase Regression and Final Acceptance

After all four phase commits exist, run:

```powershell
python -m pytest misc/PELICAN_mvp/tests
```

Also manually rerun the product scenarios from `temp/discuss.md`:

```text
1. Tutor asks which Meiji reform most affected old class structures; learner answers "廢藩置縣?"
2. Tutor mentions a turning point; learner asks "什麼轉折點?"
3. Learner says "我不太懂" during a concept explanation.
4. Learner says "好" after an interruption.
5. Learner gives a partial humanities explanation.
```

Acceptance outcomes:

```text
- `LearningManagerOrchestrator` is the turn-level decision owner.
- `PelicanEngine` remains the state mutation, persistence, and pipeline event owner.
- Specialist agents are consumed as capabilities rather than fixed job takers.
- Learner-facing tutor responses default to `google/gemini-3.5-flash-lite`.
- Orchestrator decisions default to `google/gemini-3.5-flash-lite`.
- Skill generation model routing remains separate.
- Structured-output support is probed and fallback behavior is deterministic.
- Route legality is enforced by a tested matrix.
- Confidence threshold and tiebreaker behavior are documented and tested.
- Clarification and interruption routes do not write mastery evidence.
- Same-turn logs expose safe route decisions without raw learner text or model output.
```

Before final handoff, run `git status --short` and review `git log --oneline -4` to confirm the four phase commits exist in order and no planned files remain uncommitted. Remaining deployment decisions: whether production should set `PELICAN_ORCHESTRATOR_MODEL` explicitly, whether `PELICAN_TUTOR_MODEL` should be pinned in environment rather than relying on code defaults, and whether live OpenRouter structured-output health checks should run at startup, on demand, or only in diagnostics.
