# Agentic PELICAN Methods Blueprint Implementation Plan

This revised plan implements the Methods blueprint from `docs/paper_draft/paper.md` as a causal, inspectable MVP rather than only an observability layer. The audit in `/workspaces/AREQA/temp/discuss.md` found that the earlier plan would expose traces and artifacts, but would not guarantee the paper's claimed order: learner evidence updates state and GUM, EDF decides from that updated evidence, and the tutor response is generated from the current policy. The revised phase order fixes that contract first, then adds typed proposals, six-stage methodology tracing, EDF/GUM-conditioned tutoring, and a UI that visualizes the paper graph.

The implementation remains inside `misc/PELICAN_mvp`. It preserves the current `PelicanEngine` architecture, fixture curricula, rule-mode offline behavior, local JSON persistence, and static frontend. LLM output remains a bounded proposal source only; raw learner answers, raw prompts, raw model output, API keys, credentials, and provider response bodies must not enter structured logs, pipeline traces, agent proposal records, or public API metadata.

## Scope and Non-Goals

- Implement the Section III / Figure 1 runtime contract in the existing FastAPI/static MVP.
- Use the six core Figure 1 stages: Goal Framing, Skill Construction, Cognitive Diagnosis, Knowledge State Update, EDF Strategy Selection, and Tutor Response.
- Treat GUM memory as a supporting subsystem and learner chat as interaction events linked to tutoring cycles, not extra core pipeline stages.
- Store bounded, safe methodology metadata in `SessionState`; do not store raw transcript data in traces or artifacts.
- Add persistence migration and load-time validation because the plan adds durable session fields.
- Add learner-visible progress snapshots with richer status/confidence metadata.
- Do not implement an empirical study, production deployment, AREQA backend integration, or a new orchestration framework.

### Phase 1: Runtime Contract, IDs, and Persistence Migration

#### Problem

The current plan adds trace and artifact lists before defining the causal contract they must prove. Without stable `turn_id`, `cycle_id`, sequence ordering, proposal IDs, status values, schema migration, and safe deserialization bounds, later trace records can become historically misleading. Session resume can re-present a diagnostic and accidentally create new methodology events without a new learner turn.

#### Assumptions

- `SessionState` is the authoritative local persistence boundary.
- Existing persisted sessions use schema version 2 and must load with compatibility defaults.
- New methodology records must be bounded, enum-validated, and safe for API display.
- A tutoring cycle starts when the system accepts a learner input that may affect diagnosis, memory, EDF, or tutor output.
- If a legacy session lacks IDs or methodology records, the loader may initialize empty collections and create IDs only on the next learner turn.

#### Solution

Add the durable contract types before changing behavior. Introduce `turn_id`, `cycle_id`, monotonic methodology sequence numbers, safe record statuses, and bounded methodology collections. Bump the persisted schema version and make deserialization fail closed for malformed methodology records while preserving the rest of the session whenever possible.

#### Implementation

> Context: Add Google-style docstrings to every new or materially changed public model, class, and function. Document the ID invariants, sequence ownership, schema compatibility, bounds, enum validation, and privacy rules. Inline comments should explain only non-obvious state-boundary decisions, such as why malformed methodology records are dropped instead of raising during legacy load. Structured logs must use `log_event()` with stable event names, correlation IDs, schema version, result status, and safe reason codes only.

Modify `pelican_mvp/models.py`.

- Add proposed enums:
  - `MethodologyStage`: `GOAL_FRAMING`, `SKILL_CONSTRUCTION`, `COGNITIVE_DIAGNOSIS`, `KNOWLEDGE_STATE_UPDATE`, `EDF_STRATEGY_SELECTION`, `TUTOR_RESPONSE`.
  - `MethodologyEventType`: `PIPELINE_STAGE`, `GUM_SUBSYSTEM`, `LEARNER_INTERACTION`, `AGENT_PROPOSAL`.
  - `MethodologyStatus`: `STARTED`, `COMPLETED`, `REJECTED`, `SKIPPED`, `FAILED`.
  - `ProposalValidationStatus`: `PENDING`, `ACCEPTED`, `REJECTED`, `FALLBACK_USED`.
- Add proposed `MethodologyRef` dataclass for safe references:
  - `ref_type: str`
  - `ref_id: str`
  - `label: str`
- Add `turn_id: str | None`, `cycle_id: str | None`, and `methodology_sequence: int` to `SessionState`.
- Add empty bounded collections to `SessionState` for later phases:
  - `methodology_events: list[Any]`
  - `agent_proposals: list[Any]`
  - `learner_progress: dict[str, Any]`
- Update `SessionState.to_dict()` and `SessionState.from_dict()` with version-aware defaults and bounds.

Modify `pelican_mvp/state_store.py`.

- Bump `SUPPORTED_SCHEMA_VERSION` from `2` to `3`.
- Preserve schema version 2 compatibility by loading missing methodology fields with defaults.
- Validate loaded methodology collection lengths and entry shapes before constructing `SessionState`.

Modify `pelican_mvp/observability.py`.

- Add only safe correlation fields to `_SAFE_FIELDS`: `turn_id`, `cycle_id`, `sequence`, `proposal_id`, `schema_version`, `methodology_status`, and `reason_code`.
- Do not allow free-form summaries as structured-log fields.

Modify `pelican_mvp/engine.py`.

- Add proposed private helpers:
  - `_begin_turn()` to create or advance `turn_id`, `cycle_id`, and sequence state when a learner message is accepted.
  - `_next_methodology_sequence()` to allocate monotonic sequence numbers.
  - `_bounded_append(collection_name, item, limit)` to centralize caps.
- Call `_begin_turn()` only after `respond()` accepts a non-empty learner message.
- Ensure `start()` and diagnostic resume paths do not create new turn or cycle IDs.

#### Expected File Tree After Phase 1

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── engine.py                      [modified]
│   ├── models.py                      [modified]
│   ├── observability.py               [modified]
│   └── state_store.py                 [modified]
└── tests/
    ├── test_engine.py                 [modified]
    ├── test_models.py                 [modified]
    └── test_state_store.py            [modified]
```

#### Work List

1. [ ] Modify `pelican_mvp/models.py`.
   - [ ] Add proposed `MethodologyStage`, `MethodologyEventType`, `MethodologyStatus`, and `ProposalValidationStatus`.
   - [ ] Add proposed `MethodologyRef` with safe serialization.
   - [ ] Add `SessionState.turn_id`, `SessionState.cycle_id`, `SessionState.methodology_sequence`, `SessionState.methodology_events`, `SessionState.agent_proposals`, and `SessionState.learner_progress`.
   - [ ] Update `SessionState.to_dict()` and `SessionState.from_dict()` with schema-compatible defaults and collection caps.
2. [ ] Modify `pelican_mvp/state_store.py`.
   - [ ] Update proposed `SUPPORTED_SCHEMA_VERSION = 3`.
   - [ ] Preserve schema version 2 loading behavior for existing local sessions.
   - [ ] Add load-time validation for methodology fields, enum values, list lengths, and safe string lengths.
3. [ ] Modify `pelican_mvp/observability.py`.
   - [ ] Add only correlation and status fields to `_SAFE_FIELDS`.
   - [ ] Keep free-form summaries out of structured logs.
4. [ ] Modify `pelican_mvp/engine.py`.
   - [ ] Add proposed `PelicanEngine._begin_turn()`.
   - [ ] Add proposed `PelicanEngine._next_methodology_sequence()`.
   - [ ] Add proposed `PelicanEngine._bounded_append()`.
   - [ ] Call `_begin_turn()` from `respond()` after empty-message validation and before phase-specific handlers.
   - [ ] Confirm `start()` and `_present_next_diagnostic()` do not allocate new turns on resume.
5. [ ] Modify `tests/test_models.py`.
   - [ ] Add serialization compatibility tests for schema version 2 payloads without methodology fields.
   - [ ] Add enum validation tests for malformed methodology status/stage values.
6. [ ] Modify `tests/test_state_store.py`.
   - [ ] Add migration tests for version 2 persisted sessions.
   - [ ] Add malformed methodology collection tests proving invalid entries are bounded or dropped safely.
7. [ ] Modify `tests/test_engine.py`.
   - [ ] Assert `respond()` creates a new `turn_id` and `cycle_id`.
   - [ ] Assert `start()` resume does not allocate a new turn or duplicate cycle state.

#### Test Plan

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_models.py tests/test_state_store.py tests/test_engine.py -q
```

Required assertions:

- Existing version 2 state payloads load successfully with empty methodology collections.
- Version 3 state payloads preserve methodology contract fields.
- Malformed methodology entries do not crash session load.
- Accepted learner messages allocate turn/cycle IDs once per turn.
- Resume/start paths do not create learner turns.

#### Expected Output / Result

The MVP has a durable methodology contract: every later event or proposal can be linked to a learner turn and tutoring cycle, persisted safely, and loaded across schema versions. No visible teaching behavior changes yet.

#### Testing Script

##### Act 01: Load Legacy State

Load a schema version 2 session dictionary without methodology fields.

Pass condition: `SessionState.from_dict()` returns a valid state with empty methodology fields and schema version 3 on re-serialization.

##### Act 02: Accept Learner Input

Create an engine, call `start()`, then call `respond("深度學習")`.

Pass condition: the accepted learner message has a non-empty `turn_id`, `cycle_id`, and a stable starting sequence value.

##### Act 03: Resume Without New Turn

Persist a diagnosis session, create a new engine for the same store, and call `start()`.

Pass condition: no new `turn_id` is allocated and methodology sequence is unchanged.

#### Gate to Enter the Next Phase

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_models.py tests/test_state_store.py tests/test_engine.py -q
python -m pytest -q --ignore=tests/test_e2e.py
git diff --check
```

Every command must pass. If any migration or ID test fails, fix this phase before adding trace or proposal records.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): add methodology runtime contract
```

Before committing:

1. Inspect `git status --short` and preserve unrelated user changes.
2. Stage only Phase 1 files or exact hunks in `pelican_mvp/models.py`, `pelican_mvp/state_store.py`, `pelican_mvp/observability.py`, `pelican_mvp/engine.py`, and listed tests.
3. Run `git diff --cached --check`.
4. Review `git diff --cached --stat`.
5. Commit with the message above.
6. Confirm with `git show --stat --oneline --summary HEAD`.

### Phase 2: Causal Tutoring Transaction and Learner Progress

#### Problem

The current tutoring path can select a strategy before recording the learner's current evidence and reevaluating EDF. That contradicts the paper's required order: learner evidence, knowledge/GUM update, EDF decision, then tutor response. The current knowledge model also has only `UNDIAGNOSED`, `MASTERED`, and `NOT_MASTERED`, while the paper's progress snapshot needs more expressive learner-visible state.

#### Assumptions

- Direct evidence should update the current node before strategy selection.
- Generated plans must support prerequisite inference, not only fixture curricula.
- Richer progress statuses must remain backward compatible with existing tree rendering.
- If prerequisite inference is uncertain, inferred states should be lower-confidence and distinguishable from direct mastery.
- Rule mode must remain deterministic.

#### Solution

Refactor the tutoring transaction so the current answer causally affects the current strategy. Add richer knowledge/progress states and generated-plan prerequisite inference. Add a learner progress snapshot API model that separates direct evidence, inferred prerequisite evidence, confidence, and visible status.

#### Implementation

> Context: Add Google-style docstrings to new and materially changed diagnosis, engine, and model functions. Document the exact tutoring transaction order, direct-versus-inferred evidence semantics, confidence rules, and fallback behavior. Inline comments should explain only high-risk ordering or inference decisions. Structured logs must record safe event names and reason codes for state update, EDF evaluation, and progress snapshot refresh; never log raw answers.

Modify `pelican_mvp/models.py`.

- Extend `KnowledgeStatus` with proposed values:
  - `PARTIALLY_MASTERED`
  - `FRAGILE`
  - `INFERRED_MASTERED`
- Add proposed `LearnerProgressNode` dataclass:
  - `node_id: str`
  - `label: str`
  - `status: KnowledgeStatus`
  - `confidence: float`
  - `evidence_source: str`
  - `direct_evidence_count: int`
  - `inferred_from: tuple[str, ...] = ()`
- Add proposed `LearnerProgressSnapshot` dataclass:
  - `cycle_id: str | None`
  - `current_node_id: str | None`
  - `nodes: tuple[LearnerProgressNode, ...]`
  - `updated_at: str`

Modify `pelican_mvp/diagnosis.py`.

- Update `apply_diagnostic_result()` so generated plans can infer prerequisite state when the skill graph exposes prerequisite relationships.
- Preserve fixture-specific behavior while making the inference path source-independent.
- Add reason codes for direct mastery, direct non-mastery, inferred prerequisite mastery, partial mastery, and fragile mastery.

Modify `pelican_mvp/engine.py`.

- Refactor `_handle_tutoring()` to use this order:
  1. classify learner response
  2. apply knowledge-state evidence for the current node when applicable
  3. record GUM direct evidence
  4. evaluate EDF from updated evidence
  5. build strategy context
  6. select strategy
  7. generate tutor response
  8. persist atomically
- Update `_handle_diagnostic()` so diagnostic answers also refresh GUM, EDF, progress snapshot, and central tutor-response issuance when the next response is a tutor prompt.
- Add proposed `_refresh_learner_progress()` to populate `SessionState.learner_progress`.
- Add proposed `_issue_tutor_response()` as the central place to record tutor-response methodology events later, covering both `_handle_tutoring()` and `_present_next_diagnostic()` paths.

Modify `pelican_mvp/edf_simulator.py`.

- Confirm `evaluate()` consumes the updated direct evidence count and latest response category.
- Add explicit tests or minor API adjustment only if needed to guarantee current-turn evidence is included.

Modify `pelican_mvp/server.py`.

- Add `learning.progress_snapshot` to `_learning_metadata()` using safe progress fields only.

#### Expected File Tree After Phase 2

This tree is cumulative from Phase 1.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── diagnosis.py                   [modified]
│   ├── edf_simulator.py               [modified, only if API adjustment is needed]
│   ├── engine.py                      [modified]
│   ├── models.py                      [modified]
│   └── server.py                      [modified]
└── tests/
    ├── test_diagnosis.py              [modified]
    ├── test_edf_simulator.py          [modified, only if edf_simulator.py changes]
    ├── test_engine.py                 [modified]
    ├── test_models.py                 [modified]
    └── test_server.py                 [modified]
```

#### Work List

1. [ ] Modify `pelican_mvp/models.py`.
   - [ ] Extend `KnowledgeStatus` with proposed richer statuses.
   - [ ] Add proposed `LearnerProgressNode`.
   - [ ] Add proposed `LearnerProgressSnapshot`.
   - [ ] Update tree/progress serialization compatibility.
2. [ ] Modify `pelican_mvp/diagnosis.py`.
   - [ ] Update `apply_diagnostic_result()` to infer prerequisite mastery for generated and fixture plans.
   - [ ] Add safe reason codes for direct, inferred, partial, and fragile state changes.
3. [ ] Modify `pelican_mvp/engine.py`.
   - [ ] Reorder `_handle_tutoring()` to update state, GUM, and EDF before strategy selection.
   - [ ] Update `_handle_diagnostic()` to refresh GUM, EDF, and learner progress from diagnostic evidence.
   - [ ] Add proposed `PelicanEngine._refresh_learner_progress()`.
   - [ ] Add proposed `PelicanEngine._issue_tutor_response()`.
   - [ ] Ensure state persistence happens after the ordered transaction completes.
4. [ ] Modify `pelican_mvp/edf_simulator.py` only if needed.
   - [ ] Adjust `evaluate()` or its caller so current-turn evidence is included in the EDF snapshot.
5. [ ] Modify `pelican_mvp/server.py`.
   - [ ] Add `learning.progress_snapshot` to `_learning_metadata()`.
6. [ ] Modify `tests/test_diagnosis.py`.
   - [ ] Add generated-plan prerequisite inference coverage.
   - [ ] Add richer status transition coverage.
7. [ ] Modify `tests/test_engine.py`.
   - [ ] Add a causal regression proving the current learner answer changes the current EDF policy and selected strategy.
   - [ ] Add coverage for `_present_next_diagnostic()` issuing tutor responses through the central response path.
8. [ ] Modify `tests/test_server.py`.
   - [ ] Assert `learning.progress_snapshot` contains safe progress metadata.
9. [ ] Modify `tests/test_models.py`.
   - [ ] Add serialization tests for richer knowledge statuses and progress snapshots.

#### Test Plan

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_diagnosis.py tests/test_engine.py tests/test_models.py tests/test_server.py -q
python -m pytest tests/test_edf_simulator.py -q
```

Required assertions:

- Current-turn evidence is visible to EDF before strategy selection.
- Generated plans infer prerequisite state when applicable.
- Progress snapshots distinguish direct and inferred mastery.
- First diagnostic-to-tutoring transition uses the same tutor-response issuance path as tutoring turns.
- API progress metadata contains no raw learner answer.

#### Expected Output / Result

The engine follows the paper's causal transaction. A learner answer can immediately update knowledge state, GUM evidence, EDF policy, learner progress, and the current tutor strategy. Generated learning plans now support prerequisite inference.

#### Testing Script

##### Act 01: Current Evidence Affects Current Strategy

Run a session into tutoring, submit a difficulty answer such as `我不會`, and inspect the resulting EDF snapshot and strategy.

Pass condition: the selected strategy reflects the EDF policy computed from that same answer, not the previous turn.

##### Act 02: Generated Prerequisite Inference

Create a generated deep-learning plan with a prerequisite relation and answer the successor diagnostic correctly.

Pass condition: the prerequisite node is marked with inferred or partial mastery metadata instead of remaining unchanged.

##### Act 03: Progress Snapshot API

Call `/api/respond` after diagnostic evidence.

Pass condition: `learning.progress_snapshot` includes current node status, confidence, and evidence source without raw text.

#### Gate to Enter the Next Phase

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_diagnosis.py tests/test_engine.py tests/test_models.py tests/test_server.py tests/test_edf_simulator.py -q
python -m pytest -q --ignore=tests/test_e2e.py
git diff --check
```

Every command must pass. Do not proceed until the causal ordering regression passes.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): enforce causal tutoring transaction
```

Before committing:

1. Inspect `git status --short` and preserve unrelated user changes.
2. Stage only Phase 2 files or exact hunks.
3. Run `git diff --cached --check`.
4. Review `git diff --cached --stat`.
5. Commit with the message above.
6. Confirm with `git show --stat --oneline --summary HEAD`.

### Phase 3: Typed Agent Proposals and Skill Generation Results

#### Problem

The paper says agentic components produce proposals that are validated before state mutation. The previous plan mostly recorded artifacts after mutation, which proves a module ran but not that a bounded proposal was validated. The current skill generator also hides rejected attempts and fallback reasons behind `generate() -> tuple[DomainSkill, str]`, so the engine cannot expose rejected Skill Agent proposals.

#### Assumptions

- The engine remains the only component allowed to mutate `SessionState`.
- Proposals are bounded metadata envelopes, not raw LLM payloads.
- Existing `DomainSkillGenerator.generate(topic) -> tuple[DomainSkill, str]` compatibility must remain available.
- Validation rejection should lead to deterministic fallback, not session failure, unless no safe fallback exists.

#### Solution

Introduce typed `AgentProposal` envelopes with validation status, proposal IDs, turn/cycle correlation, role, stage, payload references, and safe reason codes. Refactor state-changing paths to follow propose, validate, apply/reject. Add a structured `SkillGenerationResult` so accepted and rejected skill proposals are visible without exposing raw model content.

#### Implementation

> Context: Add Google-style docstrings to new proposal/result models and materially changed generator/engine methods. Document that proposal payloads are references and safe summaries only, not raw content. Explain validation status transitions, fallback semantics, and why proposals must be recorded before mutation. Inline comments should explain only non-obvious proposal validation boundaries. Structured logs must include proposal IDs, role, stage, validation status, and safe reason codes, without free-form summaries.

Modify `pelican_mvp/models.py`.

- Add proposed `AgentRole` enum:
  - `INTAKE_AGENT`
  - `SKILL_AGENT`
  - `DIAGNOSIS_AGENT`
  - `STATE_AGENT`
  - `POLICY_AGENT`
  - `FAST_TUTOR_AGENT`
  - `SLOW_SIMULATOR_AGENT`
- Add proposed `AgentProposal` dataclass:
  - `proposal_id: str`
  - `turn_id: str | None`
  - `cycle_id: str | None`
  - `sequence: int`
  - `role: AgentRole`
  - `stage: MethodologyStage`
  - `artifact_type: str`
  - `payload_ref: MethodologyRef`
  - `validation_status: ProposalValidationStatus`
  - `reason_code: str`
  - `node_id: str | None = None`
  - `strategy: str | None = None`
  - `skill_id: str | None = None`
  - `created_at: str = ...`
- Add `to_dict()` and `from_dict()` with safe bounds.

Modify `pelican_mvp/skill_generator.py`.

- Add proposed `SkillGenerationAttempt` dataclass:
  - `attempt_index: int`
  - `route: str`
  - `validation_status: ProposalValidationStatus`
  - `reason_code: str`
- Add proposed `SkillGenerationResult` dataclass:
  - `skill: DomainSkill`
  - `route: str`
  - `attempts: tuple[SkillGenerationAttempt, ...]`
  - `used_fallback: bool`
  - `final_reason_code: str`
- Add proposed `generate_with_result(topic) -> SkillGenerationResult`.
- Keep existing `generate(topic) -> tuple[DomainSkill, str]` as a wrapper around `generate_with_result()`.

Modify `pelican_mvp/engine.py`.

- Add proposed `_record_agent_proposal()` and `_validate_agent_proposal()` helpers.
- Record proposals before applying:
  - Intake proposal before storing profile fields.
  - Skill proposal before attaching the generated/loaded skill plan.
  - Diagnosis proposal before presenting the next diagnostic node.
  - State proposal before mutating node mastery.
  - Policy proposal before applying EDF policy to strategy context.
  - Tutor proposal before returning the tutor response.
- Convert existing retrospective artifact records into proposal records with `ACCEPTED`, `REJECTED`, or `FALLBACK_USED` statuses.

Modify `pelican_mvp/server.py`.

- Expose recent proposals as `learning.agent_proposals`.
- Do not expose raw payloads; expose role, stage, status, reason code, payload ref label, node ID, strategy, and skill ID.

#### Expected File Tree After Phase 3

This tree is cumulative from Phases 1 and 2.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── engine.py                      [modified]
│   ├── models.py                      [modified]
│   ├── server.py                      [modified]
│   └── skill_generator.py             [modified]
└── tests/
    ├── test_engine.py                 [modified]
    ├── test_models.py                 [modified]
    ├── test_server.py                 [modified]
    └── test_skill_generator.py        [modified]
```

#### Work List

1. [ ] Modify `pelican_mvp/models.py`.
   - [ ] Add proposed `AgentRole`.
   - [ ] Add proposed `AgentProposal` with bounded serialization.
   - [ ] Update `SessionState.from_dict()` to load proposal records safely.
2. [ ] Modify `pelican_mvp/skill_generator.py`.
   - [ ] Add proposed `SkillGenerationAttempt`.
   - [ ] Add proposed `SkillGenerationResult`.
   - [ ] Add proposed `DomainSkillGenerator.generate_with_result()`.
   - [ ] Keep `DomainSkillGenerator.generate()` backward compatible.
3. [ ] Modify `pelican_mvp/engine.py`.
   - [ ] Add proposed `PelicanEngine._record_agent_proposal()`.
   - [ ] Add proposed `PelicanEngine._validate_agent_proposal()`.
   - [ ] Record and validate Intake Agent proposals before profile mutation.
   - [ ] Record Skill Agent accepted/rejected/fallback proposals from `SkillGenerationResult`.
   - [ ] Record Diagnosis Agent proposals before diagnostic presentation.
   - [ ] Record State Agent proposals before mastery mutation.
   - [ ] Record Policy Agent proposals before strategy selection.
   - [ ] Record Fast Tutor Agent and Slow Simulator Agent proposals before tutor response return.
4. [ ] Modify `pelican_mvp/server.py`.
   - [ ] Add `learning.agent_proposals` to `_learning_metadata()`.
   - [ ] Ensure proposal metadata is bounded and safe.
5. [ ] Modify `tests/test_skill_generator.py`.
   - [ ] Assert `generate_with_result()` exposes safe rejected-attempt metadata.
   - [ ] Assert `generate()` preserves the old tuple contract.
   - [ ] Assert fallback reasons are safe codes only.
6. [ ] Modify `tests/test_engine.py`.
   - [ ] Assert State Agent proposals are recorded before node mutation.
   - [ ] Assert rejected Skill Agent proposals appear when validation fails.
   - [ ] Assert proposal IDs correlate with the current turn/cycle.
7. [ ] Modify `tests/test_server.py`.
   - [ ] Assert `learning.agent_proposals` contains safe metadata only.
8. [ ] Modify `tests/test_models.py`.
   - [ ] Add proposal serialization, invalid enum, and length-bound tests.

#### Test Plan

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_skill_generator.py tests/test_engine.py tests/test_models.py tests/test_server.py -q
```

Required assertions:

- Proposal records exist before state mutation in critical paths.
- Skill-generation rejected attempts are available as safe metadata.
- Existing callers of `generate()` continue to work.
- API proposal output contains no raw learner answers or raw model output.
- Proposal records are correlated by `turn_id`, `cycle_id`, and `proposal_id`.

#### Expected Output / Result

The MVP can truthfully claim agentic proposal behavior: role components produce bounded proposals, the engine validates them, and only accepted proposals affect state. Rejected and fallback skill proposals become inspectable without leaking model output.

#### Testing Script

##### Act 01: Skill Proposal Rejection

Stub the LLM skill generator to return one invalid payload before fallback.

Pass condition: `generate_with_result()` returns a fallback skill and includes a rejected attempt with a safe reason code.

##### Act 02: State Proposal Before Mutation

Answer a diagnostic and inspect the proposal sequence around node status mutation.

Pass condition: a State Agent proposal with the active `cycle_id` exists before the status is changed.

##### Act 03: API Proposal Safety

Submit a unique learner answer through `/api/respond`.

Pass condition: the unique raw answer does not appear in `learning.agent_proposals`.

#### Gate to Enter the Next Phase

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_skill_generator.py tests/test_engine.py tests/test_models.py tests/test_server.py -q
python -m pytest -q --ignore=tests/test_e2e.py
git diff --check
```

Every command must pass. Do not proceed if proposal ordering or safety tests fail.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): validate typed agent proposals
```

Before committing:

1. Inspect `git status --short` and preserve unrelated user changes.
2. Stage only Phase 3 files or exact hunks.
3. Run `git diff --cached --check`.
4. Review `git diff --cached --stat`.
5. Commit with the message above.
6. Confirm with `git show --stat --oneline --summary HEAD`.

### Phase 4: Methodology Event Ledger and EDF/GUM Strategy Context

#### Problem

The previous plan used eight stage labels, including GUM and chat loop as core stages, which does not match Figure 1. It also changed strategy context without explicitly proving current evidence drives current strategy. The UI would risk showing last-known stage completion across unrelated cycles.

#### Assumptions

- Phase 1 provides turn/cycle/sequence IDs.
- Phase 2 enforces state/GUM/EDF ordering.
- Phase 3 provides proposal records for agent roles.
- GUM and learner interaction events should be shown as linked subsystem events, not as extra core stages.
- Strategy selection should remain deterministic in rule mode.

#### Solution

Add a `MethodologyEvent` ledger grouped by tutoring cycle. Record six core pipeline stages, separate GUM subsystem events, and learner interaction events. Introduce `TutoringContext` that uses the updated EDF snapshot, current learner state, current node metadata, safe recent memory signals, and plan source. Refactor `select_strategy()` to consume this context.

#### Implementation

> Context: Add Google-style docstrings to new event/context models and materially changed engine/tutoring/memory functions. Document the Figure 1 mapping, why GUM/chat are separate event types, how cycle grouping avoids misleading UI status, and how safe memory signals influence deterministic strategy selection. Inline comments should explain only policy precedence or non-obvious event placement. Structured logs must include stage, event type, cycle ID, status, strategy, and safe reason code only.

Modify `pelican_mvp/models.py`.

- Add proposed `MethodologyEvent` dataclass:
  - `event_id: str`
  - `turn_id: str | None`
  - `cycle_id: str | None`
  - `sequence: int`
  - `event_type: MethodologyEventType`
  - `stage: MethodologyStage | None`
  - `status: MethodologyStatus`
  - `source: str`
  - `input_ref: MethodologyRef | None`
  - `output_ref: MethodologyRef | None`
  - `node_id: str | None = None`
  - `strategy: str | None = None`
  - `reason_code: str = "recorded"`
  - `created_at: str = ...`
- Add proposed `TutoringContext` dataclass:
  - `category: ResponseCategory`
  - `rounds: int`
  - `pedagogical_policy: str`
  - `learner_state: str`
  - `node_id: str | None`
  - `node_label: str`
  - `recent_signals: tuple[str, ...] = ()`
  - `plan_source: PlanSource = PlanSource.GENERATED`
  - `skill_id: str | None = None`

Modify `pelican_mvp/learning_memory.py`.

- Add proposed `recent_safe_signals(state, limit=5) -> tuple[str, ...]`.
- Mark raw learner evidence as untrusted for prompt construction.
- Keep `get_working_context()` compatible, but quote or label learner text as untrusted if it is ever used in LLM context.

Modify `pelican_mvp/tutoring.py`.

- Refactor `select_strategy()` to accept `TutoringContext`.
- Keep a compatibility wrapper such as proposed `select_strategy_for_category()` only if tests or callers need it.
- Update slow-candidate scoring so repeated safe signals and EDF policy affect deterministic selection.

Modify `pelican_mvp/engine.py`.

- Add proposed `_record_methodology_event()`.
- Record six core stages:
  - Goal Framing in onboarding topic/goal/level resolution.
  - Skill Construction after plan creation/generation.
  - Cognitive Diagnosis before presenting a diagnostic node.
  - Knowledge State Update before and after state proposal application.
  - EDF Strategy Selection after EDF evaluation and before tutor strategy selection.
  - Tutor Response through `_issue_tutor_response()`.
- Record GUM as `MethodologyEventType.GUM_SUBSYSTEM`.
- Record learner messages as `MethodologyEventType.LEARNER_INTERACTION`.
- Add proposed `_tutoring_context(category, rounds) -> TutoringContext`.
- Call `select_strategy(context)` only after state, GUM, and EDF updates.

Modify `pelican_mvp/server.py`.

- Expose:
  - `learning.methodology_events`
  - `learning.methodology_stages`
  - `learning.current_cycle_id`
- Keep any legacy `learning.pipeline_trace` field only as a compatibility alias if previous consumers exist; otherwise document the rename in README.

#### Expected File Tree After Phase 4

This tree is cumulative from Phases 1 through 3.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── engine.py                      [modified]
│   ├── learning_memory.py             [modified]
│   ├── models.py                      [modified]
│   ├── server.py                      [modified]
│   └── tutoring.py                    [modified]
└── tests/
    ├── test_engine.py                 [modified]
    ├── test_learning_memory.py        [modified]
    ├── test_models.py                 [modified]
    ├── test_server.py                 [modified]
    └── test_tutoring.py               [modified]
```

#### Work List

1. [ ] Modify `pelican_mvp/models.py`.
   - [ ] Add proposed `MethodologyEvent`.
   - [ ] Add proposed `TutoringContext`.
   - [ ] Add bounded serialization for methodology events.
2. [ ] Modify `pelican_mvp/learning_memory.py`.
   - [ ] Add proposed `LearningMemorySimulator.recent_safe_signals()`.
   - [ ] Treat raw evidence text as untrusted in any prompt-facing context.
3. [ ] Modify `pelican_mvp/tutoring.py`.
   - [ ] Refactor `select_strategy()` to accept `TutoringContext`.
   - [ ] Add or preserve proposed `select_strategy_for_category()` compatibility wrapper.
   - [ ] Update slow scoring with EDF policy and safe signal labels.
4. [ ] Modify `pelican_mvp/engine.py`.
   - [ ] Add proposed `PelicanEngine._record_methodology_event()`.
   - [ ] Record six core stages only as pipeline-stage events.
   - [ ] Record GUM memory updates as subsystem events.
   - [ ] Record learner accepted messages as interaction events.
   - [ ] Add proposed `PelicanEngine._tutoring_context()`.
   - [ ] Update `_handle_tutoring()` to select strategy from the current context.
   - [ ] Update `_issue_tutor_response()` so tutor-response events are centralized.
5. [ ] Modify `pelican_mvp/server.py`.
   - [ ] Expose `learning.methodology_events`, `learning.methodology_stages`, and `learning.current_cycle_id`.
6. [ ] Modify `tests/test_tutoring.py`.
   - [ ] Add context-based selection tests for EDF policies and repeated safe signals.
7. [ ] Modify `tests/test_learning_memory.py`.
   - [ ] Add bounded safe signal extraction tests.
   - [ ] Add prompt-safety tests for untrusted raw evidence.
8. [ ] Modify `tests/test_engine.py`.
   - [ ] Assert current-cycle events include the six core stages in order when applicable.
   - [ ] Assert GUM and learner chat are separate event types.
   - [ ] Assert tutor-response events are emitted for both tutoring and diagnostic-to-tutoring paths.
9. [ ] Modify `tests/test_server.py`.
   - [ ] Assert methodology events are grouped by current cycle and contain safe fields only.

#### Test Plan

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_tutoring.py tests/test_learning_memory.py tests/test_engine.py tests/test_models.py tests/test_server.py -q
```

Required assertions:

- The methodology event ledger uses six core stages, not eight.
- GUM and learner interaction records are typed separately.
- Event sequence numbers increase monotonically within the session.
- Current-turn EDF/GUM context affects current strategy.
- First diagnostic-to-tutoring and normal tutoring both record tutor-response events.

#### Expected Output / Result

The runtime now has a cycle-grouped event ledger that matches Figure 1 and a tutoring strategy path that uses current EDF/GUM context. Reviewers can inspect one cycle without confusing it with older cycles.

#### Testing Script

##### Act 01: Six-Stage Ledger

Complete onboarding through the first diagnostic prompt.

Pass condition: current-cycle events include Goal Framing, Skill Construction, and Cognitive Diagnosis as pipeline-stage events.

##### Act 02: GUM as Subsystem

Answer a diagnostic or tutoring prompt.

Pass condition: memory update appears as `GUM_SUBSYSTEM`, not as a seventh pipeline stage.

##### Act 03: Context-Aware Strategy

Submit repeated difficulty answers in tutoring.

Pass condition: selected strategy reflects updated EDF policy and recent safe signal labels.

#### Gate to Enter the Next Phase

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_tutoring.py tests/test_learning_memory.py tests/test_engine.py tests/test_models.py tests/test_server.py -q
python -m pytest tests/test_diagnosis.py tests/test_pedagogical_flow.py -q
git diff --check
```

Every command must pass. Do not proceed to UI until event ordering and strategy-context tests pass.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): record cycle methodology events
```

Before committing:

1. Inspect `git status --short` and preserve unrelated user changes.
2. Stage only Phase 4 files or exact hunks.
3. Run `git diff --cached --check`.
4. Review `git diff --cached --stat`.
5. Commit with the message above.
6. Confirm with `git show --stat --oneline --summary HEAD`.

### Phase 5: Methodology Graph API, UI, and Documentation

#### Problem

The frontend currently shows chat, tree state, EDF policy, evidence counts, context counts, and activity badges. It does not directly show the paper's methodology graph, typed proposals, current tutoring cycle, GUM subsystem updates, or learner progress snapshot. The previous plan's UI would also risk showing stale "last stage completed" state from older cycles.

#### Assumptions

- Keep the frontend as static HTML/CSS/JS.
- Do not add React, build tooling, or frontend dependencies.
- API responses from earlier phases expose safe methodology events, proposals, and progress snapshots.
- The UI should be operational and compact, not a marketing page.
- Existing Playwright tests should remain usable.

#### Solution

Add a methodology panel that renders the six core Figure 1 stages for the current cycle, linked GUM subsystem events, recent typed agent proposals, and the learner progress snapshot. Derive status from current-cycle events only. Update README and Markdown export to document the revised architecture and safety boundaries.

#### Implementation

> Context: Keep frontend code in the existing plain JavaScript style. Add comments only where mapping API methodology metadata to visual state is non-obvious. Use `textContent` for dynamic text. Backend helper functions changed in this phase must have Google-style docstrings. Structured logs are not required for pure render code, but API/export serialization must preserve safe metadata only.

Modify `pelican_mvp/server.py`.

- Ensure `_learning_metadata()` exposes stable public fields:
  - `learning.methodology_stages`
  - `learning.methodology_events`
  - `learning.agent_proposals`
  - `learning.progress_snapshot`
  - `learning.current_cycle_id`
- Update Markdown export with safe sections:
  - Methodology Events
  - Agent Proposals
  - Learner Progress Snapshot

Modify `static/index.html`.

- Add a compact methodology panel near the existing engine status.
- Add containers:
  - `methodology-stages`
  - `methodology-subsystem-events`
  - `agent-proposals`
  - `learner-progress-snapshot`

Modify `static/app.js`.

- Add proposed `renderMethodologyStages(events, stages, currentCycleId)`.
- Add proposed `renderSubsystemEvents(events, currentCycleId)`.
- Add proposed `renderAgentProposals(proposals)`.
- Add proposed `renderLearnerProgress(snapshot)`.
- Update `handleResponse(data)` to call the new renderers.
- Use only `textContent` for dynamic methodology/proposal/progress rendering.

Modify `static/styles.css`.

- Add responsive methodology panel styles.
- Keep cards at 8px border radius or less.
- Ensure text fits in desktop and mobile layouts without overlap.

Modify `README.md`.

- Update the feature list and architecture section to describe the causal order, six-stage methodology events, typed proposals, and progress snapshot.
- Clarify that GUM and learner chat are subsystem/interaction events, not core pipeline stages.

#### Expected File Tree After Phase 5

This tree is cumulative from Phases 1 through 4.

```text
misc/PELICAN_mvp/
├── README.md                          [modified]
├── pelican_mvp/
│   └── server.py                      [modified]
├── static/
│   ├── app.js                         [modified]
│   ├── index.html                     [modified]
│   └── styles.css                     [modified]
└── tests/
    ├── test_e2e.py                    [modified]
    └── test_server.py                 [modified]
```

#### Work List

1. [ ] Modify `pelican_mvp/server.py`.
   - [ ] Stabilize methodology/proposal/progress API fields in `_learning_metadata()`.
   - [ ] Extend `_markdown_export()` with safe methodology, proposal, and progress sections.
2. [ ] Modify `static/index.html`.
   - [ ] Add `#methodology-stages`.
   - [ ] Add `#methodology-subsystem-events`.
   - [ ] Add `#agent-proposals`.
   - [ ] Add `#learner-progress-snapshot`.
3. [ ] Modify `static/app.js`.
   - [ ] Add proposed `renderMethodologyStages(events, stages, currentCycleId)`.
   - [ ] Add proposed `renderSubsystemEvents(events, currentCycleId)`.
   - [ ] Add proposed `renderAgentProposals(proposals)`.
   - [ ] Add proposed `renderLearnerProgress(snapshot)`.
   - [ ] Update `handleResponse(data)` to call all renderers.
   - [ ] Use `textContent` for every dynamic field.
4. [ ] Modify `static/styles.css`.
   - [ ] Add responsive methodology-stage styles.
   - [ ] Add proposal and progress snapshot styles.
   - [ ] Verify compact desktop and mobile layouts avoid overlap.
5. [ ] Modify `README.md`.
   - [ ] Update architecture documentation and feature list.
6. [ ] Modify `tests/test_server.py`.
   - [ ] Assert API and Markdown export include safe methodology/proposal/progress data.
7. [ ] Modify `tests/test_e2e.py`.
   - [ ] Assert the UI renders six methodology stages.
   - [ ] Assert onboarding updates current-cycle Goal, Skill, and Diagnosis.
   - [ ] Assert answering a diagnostic updates State, EDF, Tutor Response, proposals, GUM subsystem, and progress snapshot.
   - [ ] Assert mobile viewport has no overlapping methodology panel content.

#### Test Plan

Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_server.py tests/test_e2e.py -q
```

Then run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pelican_mvp --port 8000
```

Open `http://127.0.0.1:8000`, reset the session, complete deep-learning onboarding, answer the first diagnostic, submit one difficulty answer, and export Markdown.

Required assertions:

- The UI lists exactly the six core methodology stages.
- Stage status is derived from the current cycle.
- GUM subsystem and learner progress are visible but not presented as core pipeline stages.
- Agent proposals display role, status, reason code, and safe reference labels.
- Markdown export contains safe metadata only.

#### Expected Output / Result

The MVP visually and programmatically matches the paper blueprint. Users and reviewers can see the current tutoring cycle, six methodology stages, supporting GUM events, typed agent proposals, and learner progress without reading server logs or raw JSON files.

#### Testing Script

##### Act 01: Load UI

Open the app in Playwright or a browser.

Pass condition: the methodology panel is visible and lists the six core stages only.

##### Act 02: Complete Onboarding

Submit `深度學習`, `想理解原理`, and `完全沒有基礎`.

Pass condition: Goal Framing, Skill Construction, and Cognitive Diagnosis show current-cycle progress.

##### Act 03: Answer Diagnostic

Submit the expected answer for the active deep-learning diagnostic.

Pass condition: Knowledge State Update, EDF Strategy Selection, Tutor Response, GUM subsystem event, agent proposal, and learner progress snapshot update.

##### Act 04: Mobile Layout Smoke Check

Set Playwright viewport to a narrow mobile width and reload the app.

Pass condition: methodology panel, chat input, sidebar, proposals, and progress snapshot do not overlap.

#### Gate to Enter the Next Phase

This is the final feature phase. Run:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_server.py tests/test_e2e.py -q
python -m pytest -q
git diff --check
```

All commands must pass. If Playwright or browser dependencies are unavailable, document the exact dependency failure and still run the full non-E2E pytest suite. Do not declare final acceptance until E2E passes or the blocker is recorded with non-E2E evidence.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): visualize agentic methodology graph
```

Before committing:

1. Inspect `git status --short` and preserve unrelated user changes.
2. Stage only Phase 5 files or exact hunks.
3. Run `git diff --cached --check`.
4. Review `git diff --cached --stat`.
5. Commit with the message above.
6. Confirm with `git show --stat --oneline --summary HEAD`.

### Cross-Phase Regression and Final Acceptance

After all five phase commits exist, run the full regression suite:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest -q
git diff --check
git status --short
git log --oneline -5
```

Run the manual end-to-end scenario:

1. Start the app with `python -m pelican_mvp --port 8000`.
2. Open `http://127.0.0.1:8000`.
3. Reset the learner session.
4. Submit topic: `深度學習`.
5. Submit goal: `想理解原理`.
6. Submit level: `完全沒有基礎`.
7. Answer the first diagnostic with the expected foundation answer.
8. Submit one difficulty answer such as `我不會`.
9. Export Markdown.

Acceptance outcomes:

- The session starts with calibration-first onboarding.
- The skill-backed deep-learning plan compiles before diagnosis.
- The first diagnostic is foundation-level, not implementation-detail trivia.
- The engine follows the causal transaction: classify response, update knowledge state, record GUM evidence, evaluate EDF, build context, select strategy, generate tutor response, and persist.
- Generated plans support prerequisite inference and richer mastery/progress statuses.
- Agent proposals are recorded before mutation and include accepted, rejected, and fallback statuses.
- Skill-generation rejected attempts are visible as safe metadata.
- Methodology events are grouped by tutoring cycle and use the six Figure 1 stages.
- GUM and learner chat are displayed as supporting subsystem/interaction events.
- EDF/GUM updates influence tutoring strategy after learner evidence.
- The UI shows current-cycle methodology progress, recent proposals, GUM subsystem activity, and learner progress snapshot.
- Markdown export includes safe session metadata, methodology events, proposals, progress snapshot, knowledge tree, and recent activity.
- Full tests pass, or any unavailable E2E dependency is explicitly documented with the remaining non-E2E test evidence.
- `git status --short` shows no planned implementation changes left uncommitted, except unrelated user changes that were intentionally preserved.
- `git log --oneline -5` shows the five phase commits in order:
  - `feat(pelican): add methodology runtime contract`
  - `feat(pelican): enforce causal tutoring transaction`
  - `feat(pelican): validate typed agent proposals`
  - `feat(pelican): record cycle methodology events`
  - `feat(pelican): visualize agentic methodology graph`

Remaining risks and mitigations:

- Risk: Schema migration changes local JSON state shape. Mitigation: compatibility defaults, schema version 2 load tests, malformed-entry tests, and bounded deserialization.
- Risk: Proposal or event metadata exposes raw learner or model text. Mitigation: safe reference objects, no free-form summaries in structured logs, API privacy tests, and Markdown export privacy tests.
- Risk: Strategy ordering changes existing fixture behavior. Mitigation: causal engine tests plus fixture diagnosis, pedagogical flow, and full regression tests.
- Risk: Generated-plan prerequisite inference overstates mastery. Mitigation: direct versus inferred status, confidence values, and tests for lower-confidence inferred states.
- Risk: UI status appears stale across cycles. Mitigation: render current-cycle events only and test cycle filtering.
- Risk: LLM mode introduces nondeterminism. Mitigation: rule-mode tests remain authoritative; LLM tests use stubs and assert fallback/safety boundaries.

Final review checklist:

- [ ] Every phase has Problem, Assumptions, Solution, Implementation, Expected File Tree, Work List, Test Plan, Expected Output / Result, Testing Script, Gate to Enter the Next Phase, and Phase Commit sections.
- [ ] Every Implementation section starts with a phase-specific `> Context:` block.
- [ ] Every work-list item names concrete file paths and symbols or proposed new symbols.
- [ ] Every test task names concrete test files and protected behavior.
- [ ] Every phase has concrete commands and a phase-scoped commit message.
- [ ] No phase depends on uncommitted work from a future phase.
- [ ] Privacy boundaries are tested and documented.
- [ ] The plan implements `/workspaces/AREQA/temp/discuss.md` findings before UI visualization work.
