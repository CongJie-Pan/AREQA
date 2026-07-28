# Learning Manager Orchestrator Implementation Plan

This revised plan borrows the completed orchestration design from `misc/agent_mvp`: a top-level orchestrator decides whether to answer directly, call a capability, delegate to a specialist, resume the pipeline, or fall back. The six-stage PELICAN pipeline remains the deterministic state machine and safety boundary, but it should no longer be the first component that interprets every learner turn. The phase order first establishes model routing and health checks, then introduces a bounded orchestration contract, then exposes existing agents as capabilities, then wires the engine with state-safe dispatch, and finally adds regression protection and observability.

### Phase 1: Model Routes and Orchestrator Health Check

#### Problem

The learner-facing tutor route and the new `LearningManagerOrchestrator` route must use `google/gemini-3.5-flash-lite`, based on `docs/tech_docs/API_model_docs/Gemini_3.5_Flash_Lite_-_API_Pricing_&_Benchmarks_OpenRouter.md`. The current plan also depends on structured orchestration outputs, but provider compatibility should be verified before the orchestrator becomes part of the turn path.

#### Assumptions

`google/gemini-3.5-flash-lite` is the intended OpenRouter model slug for both learner-facing responses and orchestration decisions. Skill generation routes remain separate and category-routed. If live OpenRouter credentials are unavailable, tests must use fake clients and the runtime must fail closed to JSON-object prompting plus local validation.

#### Solution

Add explicit tutor and orchestrator model route resolution. Add a safe structured-output health check that classifies strict JSON schema support as supported, unsupported, unavailable, or unknown. Later phases must consult this health result before relying on strict schema output.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed public module, class, and function. Document model-route precedence, why tutor/orchestrator routes are separate from skill generation, what the health check proves, what it cannot prove, OpenRouter compatibility boundaries, and privacy rules. Do not log raw learner text, prompts, model output, credentials, provider response bodies, or hidden reasoning. Use inline comments only at fallback decisions where provider compatibility affects runtime behavior.

Modify `misc/PELICAN_mvp/pelican_mvp/llm.py` to set the tutor default to `google/gemini-3.5-flash-lite` and add an orchestrator default using the same route. Add `LlmAdapter.orchestrator_model_route()` with precedence `PELICAN_ORCHESTRATOR_MODEL`, `PELICAN_TUTOR_MODEL`, `PELICAN_LLM_MODEL`, default. Add a structured-output health helper for the orchestrator route, reusing existing safe health-check patterns.

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

1. [x] Modify `misc/PELICAN_mvp/pelican_mvp/llm.py`.
   - [x] Change the existing tutor default route to `google/gemini-3.5-flash-lite`.
   - [x] Add the proposed `DEFAULT_ORCHESTRATOR_MODEL = "google/gemini-3.5-flash-lite"`.
   - [x] Add the proposed `LlmAdapter.orchestrator_model_route()` method with documented environment precedence.
   - [x] Add the proposed `LlmAdapter.check_orchestrator_structured_output_health()` helper or extend the existing health helper with an orchestrator schema probe.
   - [x] Ensure health metadata includes only safe status, reason code, provider class, and status code.
2. [x] Modify `misc/PELICAN_mvp/tests/test_llm.py`.
   - [x] Add default tutor-route assertions.
   - [x] Add orchestrator-route precedence assertions.
   - [x] Add assertions proving skill generation route defaults are unchanged.
   - [x] Add fake provider tests for supported, unsupported, unavailable, and unknown structured-output states.

#### Test Plan

Use monkeypatched environment variables and fake OpenAI-compatible clients. Assert route precedence, default model values, skill route isolation, structured-output health classification, and safe failure metadata.

#### Expected Output / Result

Tutor responses and orchestrator decisions default to `google/gemini-3.5-flash-lite`. The system can safely determine whether strict structured output is usable for turn orchestration and can fall back deterministically when it is not.

#### Testing Script

##### Act 01: Tutor Route Default

Clear `PELICAN_TUTOR_MODEL` and `PELICAN_LLM_MODEL`, instantiate `LlmAdapter`, and call `tutor_model_route()`.

Pass condition: the returned route is `google/gemini-3.5-flash-lite`.

##### Act 02: Orchestrator Route Precedence

Set `PELICAN_ORCHESTRATOR_MODEL=custom/orchestrator`, `PELICAN_TUTOR_MODEL=custom/tutor`, and `PELICAN_LLM_MODEL=custom/legacy`, then call `orchestrator_model_route()`.

Pass condition: the returned route is `custom/orchestrator`.

##### Act 03: Structured Output Fallback

Use a fake provider response that rejects strict JSON schema for the orchestrator route.

Pass condition: the health helper returns an unsupported status with safe reason metadata and no provider body.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_llm.py`. The command must pass. Do not enter Phase 2 unless route precedence, skill route isolation, and structured-output health fallback are covered.

#### Phase Commit

Commit message: `feat(pelican): configure orchestrator model health`

Stage only `misc/PELICAN_mvp/pelican_mvp/llm.py` and `misc/PELICAN_mvp/tests/test_llm.py`. Inspect `git status --short`, preserve unrelated user changes, stage only these paths or exact hunks, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 2: Orchestrator Contract and Capability Policy

#### Problem

The previous plan treated the orchestrator too much like a route classifier. That keeps the system brittle: any unexpected learner wording must be handled by another route patch. The target architecture should let the `LearningManagerOrchestrator` interpret the current learner turn and decide whether to answer, call a specialist capability, delegate a bounded subtask, resume the pipeline, or fall back.

#### Assumptions

`LearningManagerOrchestrator` may inspect the current learner turn for decision-making, but it must not mutate `SessionState`. `PelicanEngine` remains the only component that writes state, progress, mastery evidence, methodology events, or persistence records. Safe metadata must exclude raw learner text and raw model output. The orchestrator can propose actions, but engine-side validation remains mandatory.

#### Solution

Create an orchestration contract modeled after `misc/agent_mvp`: a top-level decision object, explicit capability policies, bounded action types, confidence gates, snapshot identity, and deterministic fallback. Route legality remains as a safety guard, not the primary intelligence. The orchestrator decision should represent intent and capability choice rather than a hard-coded pipeline branch.

#### Implementation

> Context: Add Google-style docstrings for the new orchestrator module, public dataclasses, enums, validators, and methods. Document the invariant that the orchestrator proposes while the engine mutates. Document capability policy semantics, immutable turn snapshots, confidence thresholds, fallback behavior, structured-output fallback, privacy boundaries, and structured-log fields. Add inline comments only where invalid model output is rejected, capability permissions are reduced, or phase safety rules override an orchestrator proposal.

Create `misc/PELICAN_mvp/pelican_mvp/agents/learning_manager_orchestrator.py`. Define immutable `LearningManagerTurnContext`, `LearningManagerAction`, `LearningManagerDecision`, and `CapabilityPolicy`. Keep shared types local unless engine traces or exports require them in `models.py`.

Use these initial action types: `answer_directly`, `call_capability`, `delegate_capability`, `resume_pipeline`, `continue_pipeline`, `fallback_legacy_pipeline`, and `reject_illegal_action`.

Use these initial capability policies: `none`, `read`, `specialist`, and `write_proposed`. `write_proposed` is only a proposal label; actual writes still require engine validation. Add local validation for action enum, capability name, policy, confidence range, threshold, target phase, snapshot id, and safe reason code.

#### Expected File Tree After Phase 2

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      agents/
        __init__.py                               [modified]
        learning_manager_orchestrator.py          [new]
      llm.py                                      [modified]
      models.py                                   [modified if shared trace types are needed]
    tests/
      test_learning_manager_orchestrator.py       [new]
      test_agent_contract.py                      [modified]
      test_llm.py                                 [modified]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/learning_manager_orchestrator.py`.
   - [ ] Add the proposed immutable `LearningManagerTurnContext` type.
   - [ ] Add the proposed `LearningManagerAction` enum.
   - [ ] Add the proposed `CapabilityPolicy` enum with `none`, `read`, `specialist`, and `write_proposed`.
   - [ ] Add the proposed `LearningManagerDecision` type with action, capability, policy, target phase, confidence, reason code, proposal source, and snapshot id.
   - [ ] Add the proposed `LearningManagerOrchestrator.interpret_turn()` method.
   - [ ] Add validators for schema shape, enum values, confidence bounds, threshold, snapshot identity, and safe reason codes.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/llm.py`.
   - [ ] Add the proposed `LlmAdapter.orchestrate_turn_decision()` method using `orchestrator_model_route()`.
   - [ ] Use strict JSON schema only when Phase 1 health allows it.
   - [ ] Use JSON-object prompting plus local validation when strict schema support is unsupported or unknown.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/agents/__init__.py`.
   - [ ] Export `LearningManagerOrchestrator` and public context/decision types.
4. [ ] Modify `misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`.
   - [ ] Test direct-answer decisions for learner clarification.
   - [ ] Test capability-call decisions for answer diagnosis.
   - [ ] Test delegated-capability decisions for complex teaching analysis.
   - [ ] Test low-confidence fallback.
   - [ ] Test invalid schema fallback.
   - [ ] Test stale snapshot rejection.
   - [ ] Test raw learner text and model output are not copied into safe metadata.
5. [ ] Modify `misc/PELICAN_mvp/tests/test_agent_contract.py`.
   - [ ] Add contract coverage proving the orchestrator returns bounded proposal metadata and does not mutate session state.
6. [ ] Modify `misc/PELICAN_mvp/tests/test_llm.py`.
   - [ ] Add orchestrator structured-output payload validation coverage.

#### Test Plan

Use fake LLM responses and immutable context fixtures. Assert valid decisions, direct-answer intent, capability-call intent, delegated-capability intent, low-confidence fallback, invalid payload fallback, stale snapshot rejection, policy normalization, and privacy boundaries.

#### Expected Output / Result

`LearningManagerOrchestrator` can interpret a learner turn as an orchestration decision rather than a fixed pipeline route. It can propose direct answers, specialist capability calls, delegated work, pipeline continuation, or fallback while remaining state-read-only.

#### Testing Script

##### Act 01: Clarification Direct Answer

Provide a context where the learner asks what a previously mentioned term means.

Pass condition: `interpret_turn()` returns `answer_directly` or `call_capability` with a no-write policy, not an answer-diagnosis action.

##### Act 02: Active Prompt Answer

Provide a context where the active tutor prompt asks a question and the learner gives a short answer.

Pass condition: `interpret_turn()` returns `call_capability` for the diagnostic capability with confidence above threshold.

##### Act 03: Complex Teaching Request

Provide a context where the learner asks for a multi-part explanation that benefits from isolated analysis.

Pass condition: `interpret_turn()` returns `delegate_capability` with a bounded specialist policy.

##### Act 04: Stale Snapshot Rejection

Return an otherwise valid LLM decision with the wrong snapshot id.

Pass condition: the decision is rejected and converted to deterministic fallback.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py misc/PELICAN_mvp/tests/test_agent_contract.py misc/PELICAN_mvp/tests/test_llm.py`. Every focused test must pass. Do not enter Phase 3 unless action validation, capability policy, confidence handling, and stale-snapshot rejection are tested.

#### Phase Commit

Commit message: `feat(pelican): add learning manager orchestration contract`

Stage only the new orchestrator module, related exports, shared model types if added, LLM orchestration helper, and focused tests. Inspect `git status --short`, preserve unrelated user changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 3: Specialist Capability Registry

#### Problem

Existing agents and handlers are currently coupled to pipeline phases. This makes them behave like job takers inside a fixed sequence rather than reusable capabilities selected by an orchestrator. Without a capability registry, the engine will keep growing route-specific conditionals.

#### Assumptions

Existing specialist behavior should be reused rather than rewritten. Capability wrappers may call existing handlers, agents, or services, but they must expose a stable name, allowed policies, expected inputs, safe outputs, write behavior, and failure semantics. Capabilities that may write mastery evidence must be clearly separated from no-write explanation or clarification capabilities.

#### Solution

Introduce a capability registry that maps orchestration decisions to existing specialist behavior. The registry is not an autonomous tool loop; it is a typed engine-side dispatch table with policy checks. This mirrors `misc/agent_mvp` where the orchestrator sees controlled tools and child agents only when policy allows them.

#### Implementation

> Context: Add Google-style docstrings for every new capability type, registry class, adapter, and public function. Document capability ownership, policy requirements, read/write behavior, failure semantics, and privacy constraints. Use inline comments only where a wrapper intentionally adapts an existing phase handler to a narrower capability contract.

Create `misc/PELICAN_mvp/pelican_mvp/agents/learning_capabilities.py` or an equivalent local module. Define `LearningCapability`, `CapabilityRegistry`, `CapabilityRequest`, and `CapabilityResult`. Register initial capabilities for diagnosis, clarification/explanation, tutoring response generation, EDF-informed feedback, slow-simulator reasoning if available, and pipeline resume/continue. Each capability must declare whether it can write mastery evidence, whether it can emit learner-facing text, and which `CapabilityPolicy` values allow it.

#### Expected File Tree After Phase 3

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      agents/
        __init__.py                               [modified]
        learning_capabilities.py                  [new]
        learning_manager_orchestrator.py          [modified]
      engine.py                                   [modified if registry construction belongs there]
    tests/
      test_learning_capabilities.py               [new]
      test_learning_manager_orchestrator.py       [modified]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/learning_capabilities.py`.
   - [ ] Add the proposed `LearningCapability` type.
   - [ ] Add the proposed `CapabilityRequest` type.
   - [ ] Add the proposed `CapabilityResult` type.
   - [ ] Add the proposed `CapabilityRegistry` class with register, lookup, policy validation, and safe failure result methods.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/agents/learning_manager_orchestrator.py`.
   - [ ] Validate proposed capability names against the registry or a registry-provided manifest.
   - [ ] Reject or downgrade decisions whose policy cannot use the requested capability.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py` if registry construction belongs to the engine.
   - [ ] Add registry construction for existing diagnosis, clarification, tutoring, EDF, slow simulator, and pipeline continuation behavior.
   - [ ] Keep wrappers thin and reuse existing specialist implementations.
4. [ ] Create `misc/PELICAN_mvp/tests/test_learning_capabilities.py`.
   - [ ] Test capability registration and lookup.
   - [ ] Test unknown capability rejection.
   - [ ] Test policy-denied capability calls.
   - [ ] Test no-write capability metadata.
   - [ ] Test write-capable capability metadata is explicit.
5. [ ] Modify `misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`.
   - [ ] Test orchestrator decisions are rejected when they request a non-existent capability.
   - [ ] Test policy downgrades preserve deterministic fallback behavior.

#### Test Plan

Use fake capability callables and fake decisions. Assert registry lookup, policy validation, unknown capability rejection, no-write declarations, write-capable declarations, and deterministic safe failure results.

#### Expected Output / Result

Existing PELICAN specialist behavior becomes addressable as named capabilities. The orchestrator can choose capabilities flexibly, while the registry and engine enforce which capabilities are legal and whether they may write state.

#### Testing Script

##### Act 01: Known Capability Lookup

Register a fake diagnostic capability and request it with an allowed specialist policy.

Pass condition: the registry returns the capability and marks the request allowed.

##### Act 02: Unknown Capability

Request a capability name that is not registered.

Pass condition: the registry returns a safe rejected result with a stable reason code.

##### Act 03: Policy Denied

Request a write-capable capability with policy `none`.

Pass condition: the registry rejects the request before the capability callable runs.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_learning_capabilities.py misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`. Every focused test must pass. Do not enter Phase 4 unless capability names, policy checks, and safe rejection behavior are covered.

#### Phase Commit

Commit message: `feat(pelican): register learning capabilities`

Stage only the capability registry, orchestrator validation updates, registry construction hunks if added, and focused tests. Inspect `git status --short`, preserve unrelated user changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 4: Engine Wiring and State-Safe Dispatch

#### Problem

`PelicanEngine.respond()` currently routes by fixed phase first. This causes short answers, clarification questions, and learner-side wording shifts to be interpreted by brittle local rules. The highest-risk integration point is state mutation: a flexible orchestrator must not accidentally write mastery evidence or progress state through the wrong path.

#### Assumptions

`PelicanEngine` remains the only state mutation owner. The orchestrator is read-only and proposes a decision. The capability registry exposes safe metadata about whether a capability can write. Any action that writes mastery evidence must pass engine-side phase legality, snapshot identity, idempotency, and capability-policy checks.

#### Solution

Instantiate `LearningManagerOrchestrator` and `CapabilityRegistry` in `PelicanEngine`. After `_begin_turn()`, build an immutable turn context and ask the orchestrator to interpret the current turn. Then validate and dispatch through a narrow engine-owned method. Fallback must call the existing legacy phase handler and remain behaviorally equivalent.

#### Implementation

> Context: Add Google-style docstrings for every new or materially changed engine helper. Document state ownership, legal dispatch, fallback equivalence, idempotency key use, same-turn event order, mastery-write protection, and failure semantics. Use inline comments only where the engine rejects a proposal to preserve pipeline invariants or intentionally routes through a no-write path.

Modify `misc/PELICAN_mvp/pelican_mvp/engine.py` to create `self.learning_manager_orchestrator` and `self.learning_capabilities`. Add helpers such as `_learning_manager_turn_context()`, `_legacy_phase_handler()`, `_validate_orchestrator_decision()`, `_dispatch_orchestrator_decision()`, and `_assert_no_mastery_write_for_no_write_capability()` if useful. Keep existing `_handle_diagnostic()`, `_handle_tutoring()`, onboarding handlers, and generated content handlers reusable.

#### Expected File Tree After Phase 4

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      engine.py                                  [modified]
      agents/
        __init__.py                              [modified if needed]
        learning_capabilities.py                 [modified]
        learning_manager_orchestrator.py         [modified]
      models.py                                  [modified if route trace fields are shared]
    tests/
      test_engine.py                             [modified]
      test_pedagogical_flow.py                   [modified]
      test_chinese_history.py                    [modified]
      test_learning_capabilities.py              [modified]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py`.
   - [ ] Add `self.learning_manager_orchestrator = LearningManagerOrchestrator(self.llm)` in `PelicanEngine.__init__()`.
   - [ ] Add registry construction for `self.learning_capabilities`.
   - [ ] Add the proposed `PelicanEngine._learning_manager_turn_context()` helper.
   - [ ] Add the proposed `PelicanEngine._legacy_phase_handler()` helper.
   - [ ] Add the proposed `PelicanEngine._validate_orchestrator_decision()` helper.
   - [ ] Add the proposed `PelicanEngine._dispatch_orchestrator_decision()` helper.
   - [ ] Update `PelicanEngine.respond()` to call the orchestrator after `_begin_turn()` and before legacy phase handling.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py` dispatch paths.
   - [ ] Route diagnostic capability calls only when active prompt and phase context are legal.
   - [ ] Route clarification and explanation capabilities through no-mastery-write paths.
   - [ ] Route pipeline resume and continuation only through legal current-phase paths.
   - [ ] Route invalid, stale, low-confidence, or policy-denied decisions to fallback.
3. [ ] Modify `misc/PELICAN_mvp/tests/test_engine.py`.
   - [ ] Add fallback behavioral-equivalence tests.
   - [ ] Add same-turn idempotency tests.
   - [ ] Add engine validation tests for illegal write-capable decisions.
4. [ ] Modify `misc/PELICAN_mvp/tests/test_pedagogical_flow.py`.
   - [ ] Add a humanities flow where a short learner answer is routed to diagnosis rather than clarification.
   - [ ] Add a clarification route test proving no mastery evidence is written.
5. [ ] Modify `misc/PELICAN_mvp/tests/test_chinese_history.py`.
   - [ ] Add the Meiji-regression case where the learner answers `廢藩置縣` to the active tutor question.
   - [ ] Add the clarification-regression case where the learner asks `什麼轉折點?` and receives focused clarification without replaying the whole lesson.

#### Test Plan

Use fake orchestrator decisions for deterministic engine routing. Assert legal dispatch, fallback equivalence, current prompt handling, no-mastery-write clarification paths, idempotency, state snapshot integrity, and safe decision rejection.

#### Expected Output / Result

Learner turns are interpreted by `LearningManagerOrchestrator` before phase handlers. Short answers to active questions are treated as answer attempts. Clarification questions receive focused clarification without writing mastery evidence. Fallback decisions preserve legacy behavior.

#### Testing Script

##### Act 01: Short Answer to Active Prompt

Set a generated humanities session where the tutor asks which Meiji reform most affected old class structures. Submit `廢藩置縣`.

Pass condition: the engine applies a diagnostic capability and does not treat the answer as a clarification request.

##### Act 02: Focused Clarification

Set a generated humanities session where the previous tutor message mentions a turning point. Submit `什麼轉折點?`.

Pass condition: the engine returns a concise clarification and does not replay the whole lesson.

##### Act 03: No Mastery Write

Submit a learner clarification during a concept explanation.

Pass condition: no mastery evidence or mastery score update is recorded for that turn.

##### Act 04: Legacy Fallback Equivalence

Force the orchestrator to return `fallback_legacy_pipeline` and run an onboarding input.

Pass condition: learner-visible output and relevant state fields match the legacy path.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_engine.py misc/PELICAN_mvp/tests/test_pedagogical_flow.py misc/PELICAN_mvp/tests/test_chinese_history.py misc/PELICAN_mvp/tests/test_learning_capabilities.py misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`. All focused tests must pass. Do not enter Phase 5 if fallback equivalence, no-mastery-write clarification, route legality, and idempotency are not covered.

#### Phase Commit

Commit message: `feat(pelican): dispatch turns through learning orchestrator`

Stage only Phase 4 engine, capability, orchestrator, shared model, and test hunks. Inspect `git status --short`, preserve unrelated changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 5: Agentic Regression Scenarios and Safety Guards

#### Problem

The system has repeatedly needed local patches because tests did not cover realistic learner turns that slightly shift intent. Orchestration must be validated against real user-like conversations, not only synthetic route unit tests.

#### Assumptions

Regression coverage should include humanities learning behavior where rephrasing every answer feels unnatural, clarification should be focused, and active-prompt answers should be recognized even when short. Tests should avoid raw prompt snapshots where possible and should assert behavior, state changes, and safe traces.

#### Solution

Add regression scenarios that exercise the orchestrator as a flexible decision-maker under engine safety rules. Cover the known Meiji and WWII learning failures, plus boundary cases where the learner asks a question inside a lesson, partially answers, or requests a different explanation style.

#### Implementation

> Context: Add Google-style docstrings only for new reusable fixtures or helpers. Document why each regression exists, which prior failure it protects, and which state invariant must hold. Use inline comments sparingly to explain non-obvious fixture setup or intentionally realistic learner wording.

Extend existing tests and add fixtures for realistic generated humanities sessions. Add manual test scripts under `misc/PELICAN_mvp/docs` only if the project already keeps experiment scripts there. Add assertions for answer diagnosis, clarification, direct answer, delegated specialist work, pipeline resume, fallback, and no-mastery-write behavior.

#### Expected File Tree After Phase 5

```text
misc/
  PELICAN_mvp/
    tests/
      test_chinese_history.py                    [modified]
      test_pedagogical_flow.py                   [modified]
      test_engine.py                             [modified]
      test_learning_manager_orchestrator.py      [modified]
    docs/
      learning_manager_orchestrator_test_script.md [new if manual scripts are kept in docs]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/tests/test_chinese_history.py`.
   - [ ] Add the Meiji short-answer regression for `廢藩置縣`.
   - [ ] Add the focused clarification regression for `什麼轉折點?`.
   - [ ] Add a partial humanities explanation case that receives helpful feedback without forcing an immediate full rephrase.
2. [ ] Modify `misc/PELICAN_mvp/tests/test_pedagogical_flow.py`.
   - [ ] Add a learner question during explanation that should trigger direct clarification.
   - [ ] Add a learner answer after clarification that resumes pipeline progression.
3. [ ] Modify `misc/PELICAN_mvp/tests/test_engine.py`.
   - [ ] Add no-mastery-write assertions for all no-write capability decisions.
   - [ ] Add fallback equivalence assertions for low-confidence and invalid decisions.
4. [ ] Modify `misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`.
   - [ ] Add table-driven action-selection cases for answer, clarification, direct answer, delegated capability, and fallback.
5. [ ] Create `misc/PELICAN_mvp/docs/learning_manager_orchestrator_test_script.md` if manual validation docs are appropriate.
   - [ ] Add Traditional Chinese realistic learner prompts.
   - [ ] Add expected decision, capability, state-write behavior, and learner-visible response criteria.

#### Test Plan

Run focused test files with fake LLM decisions where deterministic behavior is required and real prompt-level tests where the project already supports them. Assert learner-visible behavior, engine route application, capability choice, no-write invariants, and fallback behavior.

#### Expected Output / Result

Known conversational failures are protected by regression tests. The system behaves more like an agentic learning manager and less like a fixed classifier patched for each phrase.

#### Testing Script

##### Act 01: Meiji Active Answer

Ask the tutor question about which Meiji reform broke old class structures, then answer `廢藩置縣`.

Pass condition: the system evaluates the answer in context before asking for clarification.

##### Act 02: Turning Point Clarification

After a tutor message that mentions a turning point, ask `什麼轉折點?`.

Pass condition: the system explains the specific turning point concisely and does not restart the full explanation.

##### Act 03: Humanities Partial Understanding

Give a partial but relevant explanation after reading a humanities passage.

Pass condition: the system responds to the substance, gently fills the gap, and continues without forcing a mechanical rephrase unless pedagogically needed.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_chinese_history.py misc/PELICAN_mvp/tests/test_pedagogical_flow.py misc/PELICAN_mvp/tests/test_engine.py misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py`. Every regression must pass. Do not enter Phase 6 unless the known user-reported scenarios are covered.

#### Phase Commit

Commit message: `test(pelican): cover orchestrated learner turns`

Stage only Phase 5 regression tests and optional manual test script. Inspect `git status --short`, preserve unrelated changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Phase 6: Same-Turn Observability, Exports, and Documentation

#### Problem

An orchestration layer improves flexibility but adds control complexity. Without same-turn trace ordering and safe observability, debugging becomes harder than the fixed pipeline. Developers need to see what the orchestrator decided, what the engine accepted or rejected, which capability ran, and whether state writes were allowed.

#### Assumptions

Existing observability should use `pelican_mvp.observability.log_event`. Logs and exports must never include raw learner text, prompts, model output, provider payloads, credentials, or hidden reasoning. Progress or demo exports may include bounded action and capability labels only if they already expose methodology or proposal metadata.

#### Solution

Add structured logs and optional export metadata for orchestrator decision, validation, fallback, capability dispatch, no-write protection, and terminal response. Include `turn_id`, `cycle_id`, action, capability, policy, target phase, proposal source, confidence bucket, reason code, idempotency key, and outcome.

#### Implementation

> Context: Add Google-style docstrings for changed export or observability helpers. Document safe metadata fields, forbidden fields, event ordering, idempotency semantics, and failure handling. Add inline comments only where privacy redaction or event mapping is non-obvious.

Modify orchestrator, capability registry, and engine log call sites to emit stable events such as `pelican_learning_orchestrator_decided`, `pelican_learning_orchestrator_fallback`, `pelican_learning_orchestrator_action_rejected`, `pelican_learning_capability_selected`, `pelican_learning_capability_completed`, and `pelican_learning_capability_no_write_guarded`. Update documentation under `misc/PELICAN_mvp/docs`.

#### Expected File Tree After Phase 6

```text
misc/
  PELICAN_mvp/
    pelican_mvp/
      engine.py                                  [modified]
      agents/
        learning_capabilities.py                 [modified]
        learning_manager_orchestrator.py         [modified]
      progress.py                                [modified if exports need bounded labels]
    docs/
      learning_manager_orchestrator.md           [new]
    tests/
      test_learning_manager_orchestrator.py      [modified]
      test_learning_capabilities.py              [modified]
      test_engine.py                             [modified]
      test_e2e.py                                [modified]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/agents/learning_manager_orchestrator.py`.
   - [ ] Emit `pelican_learning_orchestrator_decided` for valid decisions.
   - [ ] Emit `pelican_learning_orchestrator_fallback` for unavailable, invalid, low-confidence, stale, or unsupported structured-output decisions.
   - [ ] Include safe confidence bucket and reason code, not raw rationale.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/agents/learning_capabilities.py`.
   - [ ] Emit `pelican_learning_capability_selected` before allowed capability execution.
   - [ ] Emit `pelican_learning_capability_completed` after success.
   - [ ] Emit safe rejection events for unknown or policy-denied capabilities.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py`.
   - [ ] Emit `pelican_learning_orchestrator_action_rejected` for illegal engine-side proposals.
   - [ ] Emit `pelican_learning_capability_no_write_guarded` when no-write paths prevent mastery evidence writes.
   - [ ] Ensure same-turn events include `turn_id`, `cycle_id`, action, capability, policy, target phase, idempotency key, proposal source, and reason code.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/progress.py` only if current export paths already include agent proposal summaries.
   - [ ] Include bounded action and capability labels without raw learner text.
5. [ ] Create `misc/PELICAN_mvp/docs/learning_manager_orchestrator.md`.
   - [ ] Document pipeline versus orchestrator versus capability ownership.
   - [ ] Document capability policy and write-safety semantics.
   - [ ] Document model routing and structured-output health checks.
   - [ ] Document debugging logs and privacy boundaries.
6. [ ] Modify `misc/PELICAN_mvp/tests/test_e2e.py`.
   - [ ] Add end-to-end coverage that a generated humanities session records same-turn orchestrator events in order.
   - [ ] Assert event metadata is bounded and excludes raw learner text.

#### Test Plan

Use monkeypatching or the existing logging test pattern to capture structured logs. Assert event names, order, safe metadata, idempotency fields, action labels, capability labels, fallback reasons, and absence of raw learner text.

#### Expected Output / Result

Developers can debug one learner turn from safe traces: orchestrator decision or fallback, engine validation, capability selection, capability completion, state-write guard, and learner-facing response are correlated by `turn_id` and `cycle_id`.

#### Testing Script

##### Act 01: Accepted Capability Trace

Run a generated humanities diagnostic turn with a fake accepted orchestrator decision.

Pass condition: logs include `pelican_learning_orchestrator_decided`, `pelican_learning_capability_selected`, and `pelican_learning_capability_completed` in order with the same `turn_id` and `cycle_id`.

##### Act 02: Fallback Trace

Run a turn where the fake LLM returns an invalid or low-confidence decision.

Pass condition: logs include `pelican_learning_orchestrator_fallback`, the engine completes fallback, and no raw learner text appears in log metadata.

##### Act 03: Documentation Trace

Open the generated documentation and compare the described ownership model against the code paths.

Pass condition: the document names `LearningManagerOrchestrator`, `PelicanEngine`, the six-stage pipeline, specialist capabilities, capability policy, Gemini 3.5 Flash Lite routing, health checks, fallback behavior, and no-write guards.

#### Gate to Enter the Next Phase

Run `python -m pytest misc/PELICAN_mvp/tests/test_learning_manager_orchestrator.py misc/PELICAN_mvp/tests/test_learning_capabilities.py misc/PELICAN_mvp/tests/test_engine.py misc/PELICAN_mvp/tests/test_e2e.py`. Then run `python -m pytest misc/PELICAN_mvp/tests` unless an unrelated pre-existing suite failure is documented before this phase. All orchestrator-related tests must pass and no privacy assertion may be weakened.

#### Phase Commit

Commit message: `docs(pelican): document learning orchestrator traces`

Stage only Phase 6 observability, export, documentation, and test hunks. Inspect `git status --short`, preserve unrelated changes, run `git diff --cached --check`, review `git diff --cached --stat`, commit once, and confirm with `git show --stat --oneline --summary HEAD`.

### Cross-Phase Regression and Final Acceptance

After all six phase commits exist, run:

```powershell
python -m pytest misc/PELICAN_mvp/tests
```

Also manually rerun the product scenarios from the recent discussion and experiment notes:

```text
1. Tutor asks which Meiji reform most affected old class structures; learner answers "廢藩置縣".
2. Tutor mentions a turning point; learner asks "什麼轉折點?"
3. Learner asks a question during a concept explanation.
4. Learner says they only partly understand a humanities explanation.
5. Learner gives a short answer after the tutor asks for reflection.
6. Learner asks for a different explanation style before continuing the knowledge map.
```

Acceptance outcomes:

```text
- `LearningManagerOrchestrator` is the turn-level decision owner.
- `PelicanEngine` remains the state mutation, persistence, pipeline, and mastery-write owner.
- The six-stage PELICAN pipeline remains the deterministic learning-state guardrail.
- Specialist agents are exposed as capabilities rather than fixed pipeline job takers.
- Capability policy controls whether an action can only think, read, call specialists, or propose a write.
- Actual state writes happen only after engine validation.
- Learner-facing tutor responses default to `google/gemini-3.5-flash-lite`.
- Orchestrator decisions default to `google/gemini-3.5-flash-lite`.
- Skill generation model routing remains separate.
- Structured-output support is probed and fallback behavior is deterministic.
- Short answers to active questions are interpreted in context.
- Clarification questions receive focused answers without replaying the whole lesson.
- Clarification and explanation routes do not write mastery evidence.
- Same-turn logs expose safe decisions, capabilities, and outcomes without raw learner text or model output.
```

Before final handoff, run `git status --short` and review `git log --oneline -6` to confirm the six phase commits exist in order and no planned files remain uncommitted. Remaining deployment decisions: whether production should set `PELICAN_ORCHESTRATOR_MODEL` explicitly, whether `PELICAN_TUTOR_MODEL` should be pinned in environment rather than relying on code defaults, whether live OpenRouter structured-output health checks should run at startup or on demand, and whether capability labels should appear in learner-facing experiment exports.
