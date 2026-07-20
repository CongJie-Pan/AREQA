# PELICAN Domain Skill Runtime Implementation Plan

This plan upgrades the isolated `misc/PELICAN_mvp` learning engine from topic-to-random-plan generation into a domain-aware teaching runtime. The current MVP has a useful persistence boundary, PELICAN successor-first diagnosis, local EDF simulation, and bounded learning evidence, but its planner accepts only a topic and its onboarding immediately asks a detailed diagnostic question. The new runtime will first classify the learner's intent, resolve a domain teaching skill, validate or generate a structured skill, compile a learner-specific knowledge tree, and only then invoke diagnosis and tutoring. The phases are ordered from contracts and safety boundaries, to deterministic skill assets and compiler behavior, to model generation/routing, to interactive teaching and evaluation so each phase remains independently testable and committable.

## Scope and Non-Goals

- All implementation is confined to `misc/PELICAN_mvp`.
- The AREQA `backend/` remains a reference for memory provenance and EDF semantics; it must not be modified by this plan.
- The first supported domain catalog is:
  - STEM conceptual/procedural/programming: deep learning, machine learning, linear algebra, calculus, data structures, algorithms, Python, and C.
  - Humanities/explanatory: Sinology/classical Chinese studies, history, legal knowledge excluding legal advice, literature, philosophy, art, and film.
  - Business: business and finance.
  - Learning language: language learning.
- `skill.yaml` is the executable source of truth. A human-readable `skill.md` renderer is optional future work and is not required for the MVP runtime.
- Skill lifecycle values are documented now as `runtime_generated`, `validated_generated`, and `approved`; MVP execution may use validated generated skills without human audit. Persistent approved-skill governance is future work.
- The model router uses the user-provided local model documentation as configuration references. It must not hard-code unsupported claims about availability or pricing.
- Legal content is educational only and must include a no-legal-advice policy in the domain skill.

### Phase 1: Domain Skill Contracts and Safety Boundary

#### Problem

The MVP has `KnowledgeNode`, `DiagnosticQuestion`, and `LearningPlanSnapshot`, but no contract above the knowledge tree that describes how a domain should be taught. `LearningPlanner.create_plan(topic)` cannot represent learning intent, learner level, domain-specific prerequisites, calibration questions, remediation, or assessment policy. As a result, a generated plan can pass graph validation while still being pedagogically unsafe: a broad request such as `深度學習` can produce an implementation-level first probe. The memory simulator also stores only counters and reconstructs context from history, so it does not explicitly preserve the AREQA distinction between direct user evidence and model inference.

#### Assumptions

- Existing serialized `SessionState` files and fixture curricula must remain loadable.
- Existing rule/LLM modes and fixture curriculum IDs such as `cnn` and `chinese_history` must retain their current behavior.
- The MVP may use standard-library parsing and validation plus the repository's existing YAML dependency if present; the implementer must inspect `requirements.txt` before selecting a parser.
- A skill is an instructional policy and domain map, not the learner's session tree. The tree is compiled later from the skill and intake profile.
- If the dependency or YAML format assumption is false, use a deterministic JSON-compatible representation or add the smallest documented dependency without changing the main system.

#### Solution

Introduce immutable, serializable domain-skill contracts and explicit intake/routing enums in the MVP. The contract will describe domain category, supported goals, intent types, prerequisite map, calibration questions, canonical path, diagnostic rules, teaching moves, remediation paths, and assessment policy. It will carry a lifecycle/status field for future approval without making audit a Phase 1 blocker. Add a local memory record contract that mirrors AREQA's source boundary: user text may become prompt-safe working evidence; EDF decisions and model interpretations remain non-user memory metadata.

The validator will enforce shape and cross-reference invariants before a skill is used: required sections, unique IDs, acyclic prerequisites, one concept per diagnostic, an intake calibration path, and remediation for `unknown`, `too_detailed`, `too_easy`, `project_goal`, and `assessment_goal`. Validation errors must fail closed to a deterministic fallback or an explicit intake clarification state, never to an unvalidated generated tree.

#### Implementation

> Context: Add Google-style docstrings to every new or materially changed public module, class, and function. Document why the skill is higher-level than a session tree, the invariant that unvalidated model output never reaches diagnosis, the distinction between user evidence and EDF inference, compatibility handling for legacy session JSON, and the legal-education boundary. Use inline comments only at non-obvious validation or state-boundary decisions. Emit safe structured events through `pelican_mvp.observability.log_event`; document event names and reason codes without logging raw topics, questions, answers, prompts, or model output.

1. [x] Create `misc/PELICAN_mvp/pelican_mvp/domain_skill.py` with proposed `DomainSkill`, `IntentType`, `DomainCategory`, `SkillLifecycle`, `CalibrationQuestion`, `TeachingMove`, `RemediationPath`, and related typed records.
   - [x] Define fields for `intent_types`, `prerequisites`, `calibration_questions`, `canonical_path`, `diagnostic_rules`, `teaching_moves`, `remediation_paths`, and `assessment_policy`.
   - [x] Implement `from_dict()`/`to_dict()` with strict required-field handling and bounded user-controlled strings.
2. [x] Create `misc/PELICAN_mvp/pelican_mvp/domain_catalog.py` with proposed `resolve_domain_category()` and `resolve_model_route()` symbols.
   - [x] Map the agreed STEM, humanities, business, and language topics to stable categories.
   - [x] Keep route slugs configurable and reference the local GPT-5.5 and Gemini Pro documentation paths in code comments or configuration metadata, not in learner-visible text.
   - [x] Define deterministic `unknown_domain` behavior that asks for clarification instead of silently selecting an unrelated teaching policy.
3. [x] Create `misc/PELICAN_mvp/pelican_mvp/skill_validator.py` with proposed `validate_domain_skill()` and safe validation error types.
   - [x] Validate unique IDs, prerequisite references, acyclicity, required calibration, single-concept diagnostics, remediation coverage, and legal-content policy.
   - [x] Reject empty paths, unbounded prompt templates, and skill data that embeds an answer in a diagnostic prompt.
4. [x] Modify `misc/PELICAN_mvp/pelican_mvp/models.py` only where required to add backward-compatible `LearningIntent`, `LearnerIntakeProfile`, `MemoryEvidenceRecord`, and session fields for skill metadata/intake progress.
   - [x] Preserve default values and `from_dict()` behavior for schema-version-2 fixture and generated sessions.
   - [x] Keep EDF snapshots separate from user-authored memory records.
5. [x] Modify `misc/PELICAN_mvp/pelican_mvp/observability.py` to allow stable safe fields for skill ID/category, intake decision, route, and validation reason codes.
6. [x] Extend `misc/PELICAN_mvp/tests/test_models.py`, add `misc/PELICAN_mvp/tests/test_domain_skill.py`, and add `misc/PELICAN_mvp/tests/test_skill_validator.py` for serialization, legacy compatibility, graph validation, remediation coverage, and log privacy.

#### Expected File Tree After Phase 1

The tree is cumulative for this phase only; later phases build on these files.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── domain_catalog.py                 [new]
│   ├── domain_skill.py                   [new]
│   ├── models.py                         [modified]
│   ├── observability.py                  [modified]
│   └── skill_validator.py                [new]
└── tests/
    ├── test_domain_skill.py              [new]
    ├── test_models.py                    [modified]
    └── test_skill_validator.py           [new]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/domain_skill.py` and implement the proposed public domain-skill contracts and serialization methods.
2. [ ] Create `misc/PELICAN_mvp/pelican_mvp/domain_catalog.py` and implement topic-category and model-route resolution with explicit unknown-domain results.
3. [ ] Create `misc/PELICAN_mvp/pelican_mvp/skill_validator.py` and implement structural, pedagogical, and privacy-safe validation.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/models.py` to add intake and direct-evidence state without changing fixture defaults or existing enum values.
5. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/observability.py` to allow-list the new safe event fields and preserve learner tokenization.
6. [ ] Extend `misc/PELICAN_mvp/tests/test_models.py` and create `misc/PELICAN_mvp/tests/test_domain_skill.py` and `misc/PELICAN_mvp/tests/test_skill_validator.py` with valid, invalid, legacy, legal-policy, and log-redaction cases.

#### Test Plan

Run `cd misc/PELICAN_mvp && python -m pytest tests/test_models.py tests/test_domain_skill.py tests/test_skill_validator.py -q`. Assert that valid skills round-trip, missing sections and cyclic graphs fail, all required mismatch signals have remediation, legal skills declare education-only scope, and log records contain event/reason metadata but no raw learner content. Run the existing model/state tests to prove schema-2 compatibility.

#### Expected Output / Result

The MVP has a typed skill contract that can be validated independently of an LLM. A malformed or pedagogically incomplete skill cannot be handed to the planner. Existing fixture sessions still load, and the persisted session can distinguish intake/skill metadata, direct user evidence, and EDF policy state.

#### Testing Script

##### Act 01: Validate a Complete Skill

Load a minimal skill containing one prerequisite chain, two calibration questions, one diagnostic per node, and all required remediation keys.

Pass condition: validation succeeds and serialization round-trips to equivalent data.

##### Act 02: Reject an Unsafe Skill

Submit a skill with a cyclic prerequisite and a diagnostic prompt containing its expected answer.

Pass condition: validation fails with stable reason codes and no diagnostic execution occurs.

##### Act 03: Preserve Legacy State

Load the existing schema-2 fixture JSON used by `tests/test_state_store.py`.

Pass condition: the state loads with its original curriculum behavior and default values for new fields.

#### Gate to Enter the Next Phase

Run:

```bash
cd misc/PELICAN_mvp
python -m pytest tests/test_models.py tests/test_state_store.py tests/test_domain_skill.py tests/test_skill_validator.py -q
python -m pytest tests/test_curriculum.py tests/test_diagnosis.py -q
git diff --check
```

All tests must pass, validation/privacy assertions must be present, and the diff must be clean. Retain the pytest summary and `git diff --check` result. On failure, fix the phase-owned code/tests before continuing; do not weaken assertions or mark the failure flaky.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes with:

```text
feat(pelican): add domain skill contracts and validation
```

Inspect `git status --short`, preserve unrelated changes, and stage only the Phase 1 paths above. Run `git diff --cached --check` and review `git diff --cached --stat`; create the commit only after both pass. Confirm it with `git show --stat --oneline --summary HEAD`. Do not amend unrelated commits or push.

#### Phase 1 Implementation Status

Completed on 2026-07-20 in commit `1043556 feat(pelican): add domain skill contracts and validation`.

Verification evidence retained from the phase gate:

```bash
cd misc/PELICAN_mvp
python -m pytest tests/test_models.py tests/test_state_store.py tests/test_domain_skill.py tests/test_skill_validator.py -q
# 26 passed

python -m pytest tests/test_curriculum.py tests/test_diagnosis.py -q
# 5 passed

git diff --check
# passed with no whitespace errors
```

The implementation follows the Phase 1 boundary: it adds the typed domain-skill contract, catalog routing metadata, skill validation, intake/direct-evidence session fields, safe logging allow-list updates, and focused tests. Production AREQA `backend/` and `frontend/` remain untouched.

### Phase 2: Deterministic Domain Skills and Skill-to-Tree Compiler

#### Problem

Even a valid schema does not create a useful learning route. The current fallback emits only `{topic} 基礎` and `{topic} 進階`, while the LLM path invents all nodes from one topic string. The engine therefore has no stable domain backbone, no distinction between conceptual, procedural, programming, explanatory, business, or language learning, and no way to compile a learner goal into a suitable PELICAN knowledge tree.

#### Assumptions

- The first demonstrable asset will be `deep_learning.yaml`, because the reported failure uses `深度學習`.
- The catalog may include aliases for the agreed first domains, but it must not claim full expert coverage for every listed topic until a skill asset exists.
- The compiler must be deterministic for the same skill and normalized intake profile; learner evidence can affect which nodes are selected, not the canonical prerequisite order.

#### Solution

Add versioned executable skills under `misc/PELICAN_mvp/domain_skills/` and a compiler that converts `DomainSkill + LearnerIntakeProfile` into `LearningPlanSnapshot`. The deep-learning skill will begin with foundations such as mathematical intuition, vectors/tensors, functions/transformations, model/forward-pass intuition, loss/error, optimization, and only later MLP implementation. It will define different paths for conceptual understanding, implementation, project, and assessment goals.

The compiler will apply a fixed high-level route and only select a small initial diagnostic target after calibration. PELICAN's successor-first algorithm remains responsible for diagnosis after compilation; it is not responsible for inventing the domain route. A deterministic generic skill/fallback will ask for clarification or provide a shallow foundation route when no catalog skill is available.

#### Implementation

> Context: Add Google-style docstrings to every new or materially changed public module, class, and function. Document why canonical paths are stable, why the compiler must not infer mastery from a goal statement, how skill lifecycle comments map to future `approved` assets, and why deep-learning implementation nodes are downstream of conceptual foundations. Emit safe events for skill load, compile success, fallback, and rejection with category/skill/version/reason codes only.

1. [x] Create `misc/PELICAN_mvp/domain_skills/deep_learning.yaml` as a validated `validated_generated`-ready seed skill.
   - [x] Add the four intent paths: conceptual, procedural/implementation, project-based, and assessment-driven.
   - [x] Add prerequisite map, calibration prompts, canonical path, one-concept diagnostics, teaching moves, remediation paths, and education-only safety notes where applicable.
2. [x] Create `misc/PELICAN_mvp/pelican_mvp/skill_loader.py` with proposed `load_skill()` and `load_catalog_skill()` symbols.
   - [x] Parse the structured asset, validate it before returning it, and fail closed on malformed or missing files.
   - [x] Bound file size and identifiers and prevent path traversal through topic-controlled input.
3. [x] Create `misc/PELICAN_mvp/pelican_mvp/skill_compiler.py` with proposed `compile_learning_plan()`.
   - [x] Normalize topic/goal/level input and compile only referenced canonical nodes.
   - [x] Generate `LearningPlanSnapshot` diagnostics and task steps from skill templates without leaking expected answers into prompts.
   - [x] Preserve deterministic IDs and prerequisite order for repeatability.
4. [x] Modify `misc/PELICAN_mvp/pelican_mvp/planner.py` so `LearningPlanner` resolves a skill and compiles it before any optional topic-level LLM fallback.
   - [x] Keep `create_plan(topic)` as a compatibility wrapper with a default intake profile.
   - [x] Add an explicit profile-aware method for new engine callers and log plan source/skill metadata.
5. [x] Add `misc/PELICAN_mvp/tests/test_skill_loader.py`, `misc/PELICAN_mvp/tests/test_skill_compiler.py`, and extend `misc/PELICAN_mvp/tests/test_planner.py`.
   - [x] Assert deep-learning first nodes are foundations, not MLP implementation.
   - [x] Assert same normalized input yields the same node IDs/order and different intent types select different paths.
   - [x] Assert malformed asset fallback is observable and does not produce a partial plan.

#### Expected File Tree After Phase 2

The tree is cumulative from Phase 1.

```text
misc/PELICAN_mvp/
├── domain_skills/
│   └── deep_learning.yaml             [new]
├── pelican_mvp/
│   ├── planner.py                     [modified]
│   ├── skill_compiler.py              [new]
│   └── skill_loader.py                [new]
└── tests/
    ├── test_planner.py                [modified]
    ├── test_skill_compiler.py         [new]
    └── test_skill_loader.py           [new]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/domain_skills/deep_learning.yaml` with the agreed domain skill sections and a stable foundation-first route.
2. [ ] Create `misc/PELICAN_mvp/pelican_mvp/skill_loader.py` and implement validated, bounded skill loading.
3. [ ] Create `misc/PELICAN_mvp/pelican_mvp/skill_compiler.py` and implement `compile_learning_plan()` for each supported intent type.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/planner.py` to use the loader/compiler while preserving `LearningPlanner.create_plan()` callers and fixture mode.
5. [ ] Create `misc/PELICAN_mvp/tests/test_skill_loader.py` and `misc/PELICAN_mvp/tests/test_skill_compiler.py`; extend `misc/PELICAN_mvp/tests/test_planner.py` for deterministic routes and safe fallback.

#### Test Plan

Run focused loader/compiler/planner tests. Assert deep learning never selects `MLP 實作` as its first node for an uncalibrated learner, canonical prerequisites are present, prompt/answer separation holds, project and assessment routes differ, and missing/invalid skills use a known safe fallback. Run all existing planner, state-store, curriculum, and diagnosis tests to preserve fixture and legacy generated-plan behavior.

#### Expected Output / Result

Entering `深度學習` produces a stable foundation-first plan. The plan's knowledge tree is a compiled session artifact derived from a domain teaching skill and learner intent, rather than a random list returned directly by a general model.

#### Testing Script

##### Act 01: Compile an Uncalibrated Deep-Learning Route

Compile `深度學習` with the default conceptual intent and no known mastery.

Pass condition: the first diagnostic targets a foundational concept and no MLP implementation node is selected.

##### Act 02: Compile an Implementation Route

Compile the same topic with `implementation` intent.

Pass condition: implementation nodes exist but retain their declared foundation prerequisites and do not bypass them.

##### Act 03: Reject a Broken Skill Asset

Point the loader at a skill with an unknown prerequisite ID.

Pass condition: the loader returns a safe failure/fallback event and the planner does not persist a partial tree.

#### Gate to Enter the Next Phase

```bash
cd misc/PELICAN_mvp
python -m pytest tests/test_planner.py tests/test_skill_loader.py tests/test_skill_compiler.py tests/test_state_store.py -q
python -m pytest tests/test_curriculum.py tests/test_diagnosis.py tests/test_engine.py -q
git diff --check
```

All focused and compatibility tests must pass. Retain evidence that deep-learning routing is foundation-first and deterministic. Do not begin model generation until the deterministic catalog/compiler works with no API key.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): compile deterministic domain learning routes
```

Inspect status, stage only Phase 2 paths/hunks, run `git diff --cached --check` and `git diff --cached --stat`, commit, then confirm with `git show --stat --oneline --summary HEAD`.

#### Phase 2 Implementation Status

Completed on 2026-07-20 in commit `5bbd65f feat(pelican): compile deterministic domain learning routes`.

Verification evidence retained from the phase gate:

```bash
cd misc/PELICAN_mvp
python -m pytest tests/test_planner.py tests/test_skill_loader.py tests/test_skill_compiler.py tests/test_state_store.py -q
# 27 passed

python -m pytest tests/test_curriculum.py tests/test_diagnosis.py tests/test_engine.py -q
# 13 passed

git diff --check
# passed with no whitespace errors
```

Additional compatibility check retained after the phase gate:

```bash
python -m pytest tests/test_models.py tests/test_domain_skill.py tests/test_skill_validator.py -q
# 16 passed
```

The implementation follows the Phase 2 boundary: it adds a deterministic deep-learning skill asset, validated skill loading, skill-to-plan compilation, planner skill-first routing, and focused loader/compiler/planner tests. It preserves fixture behavior and does not start model-generated skill routing yet.

### Phase 3: Skill Generation and Domain Model Routing

#### Problem

The current `LlmAdapter` has one global `PELICAN_LLM_MODEL` and sends a generic course-planner prompt. It does not route by domain, generate a skill as an intermediate artifact, validate skill output, or retry safely when the model returns invalid JSON. Sending a powerful model's free-form plan directly to the teacher would preserve the current failure mode at a higher cost.

#### Assumptions

- OpenRouter remains the optional OpenAI-compatible transport already used by `LlmAdapter`.
- The requested routing targets are `openai/gpt-5.5` for STEM/procedural/programming and `~google/gemini-pro-latest` for humanities, business, and language learning, as recorded in the local model documents. Exact availability and pricing are deployment-time concerns.
- Generated skills are session-scoped by default and carry `runtime_generated` or `validated_generated`; no automatic promotion to `approved` occurs in the MVP.
- An LLM outage, unsupported response format, or validator failure must preserve offline deterministic operation.

#### Solution

Add a skill-generation adapter that asks the selected expert model to produce the structured skill contract, not a direct student-facing lesson. Route from the resolved domain category, validate the response, and only pass validated output to the compiler. Prefer a checked-in catalog skill; use model generation for missing domains or explicit regeneration. Keep the model route configurable through environment variables with category-specific defaults, and retain the existing global model setting as a compatibility override.

The generator must request an evidence-aware domain map, stable teaching methodology, calibration questions, mismatch handling, and assessment policy. It must not request hidden reasoning or log model output. Legal skills must contain educational-only/no-legal-advice constraints. Invalid output gets one bounded retry or a deterministic fallback, with safe reason codes.

#### Implementation

> Context: Add Google-style docstrings to every new or materially changed public module, class, and function. Document the compiler boundary, route selection precedence, retry/idempotency behavior, model-output privacy boundary, and why model reasoning is not persisted. Require structured events for route selection, generation attempt, validation rejection, retry, and fallback; events must contain only safe category/route/status/reason fields.

1. [x] Modify `misc/PELICAN_mvp/pelican_mvp/llm.py` to add structured `generate_domain_skill()` support and preserve existing diagnostic/classification/tutor methods.
   - [x] Add category-specific model route resolution with environment overrides such as `PELICAN_STEM_MODEL` and `PELICAN_HUMANITIES_MODEL`.
   - [x] Keep timeout, JSON parsing, and `LlmUnavailable` behavior fail-safe.
2. [x] Create `misc/PELICAN_mvp/pelican_mvp/skill_generator.py` with proposed `DomainSkillGenerator.generate()`.
   - [x] Generate only the structured schema, bounded to one retry after validation failure.
   - [x] Load a checked-in skill before generation when one exists unless regeneration is explicitly requested.
   - [x] Set lifecycle/status metadata correctly and never auto-mark `approved`.
3. [x] Modify `misc/PELICAN_mvp/pelican_mvp/planner.py` to call the skill generator only after catalog resolution and to compile validated output.
4. [x] Modify `misc/PELICAN_mvp/pelican_mvp/models.py`/`state_store.py` to persist skill ID, version, lifecycle, category, and route metadata without persisting raw model reasoning.
5. [x] Add `misc/PELICAN_mvp/tests/test_skill_generator.py` and extend `misc/PELICAN_mvp/tests/test_llm.py` and `misc/PELICAN_mvp/tests/test_planner.py`.
   - [x] Mock route selection and model calls; assert STEM/humanities/business/language mapping.
   - [x] Assert invalid output retries once then falls back, and model text is absent from logs/state metadata.

#### Expected File Tree After Phase 3

The tree is cumulative from Phases 1 and 2.

```text
misc/PELICAN_mvp/pelican_mvp/
├── llm.py                         [modified]
├── models.py                      [modified]
├── planner.py                     [modified]
├── skill_generator.py             [new]
└── state_store.py                 [modified]
misc/PELICAN_mvp/tests/
├── test_llm.py                    [modified]
├── test_planner.py                [modified]
└── test_skill_generator.py        [new]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/llm.py` to expose category-aware skill generation and configurable model routes while retaining current adapter fallback behavior.
2. [ ] Create `misc/PELICAN_mvp/pelican_mvp/skill_generator.py` with bounded generation, validation, retry, catalog preference, and lifecycle assignment.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/planner.py` to compile only validated skills and preserve deterministic operation without credentials.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/models.py` and `misc/PELICAN_mvp/pelican_mvp/state_store.py` to persist safe skill metadata and load legacy sessions.
5. [ ] Extend `misc/PELICAN_mvp/tests/test_llm.py` and `misc/PELICAN_mvp/tests/test_planner.py`; create `misc/PELICAN_mvp/tests/test_skill_generator.py` for route, retry, fallback, and privacy assertions.

#### Test Plan

Use mocked `LlmAdapter` responses so tests are deterministic and offline. Assert each agreed domain category selects the intended configurable route, the checked-in deep-learning skill avoids a network call, invalid generated skills are retried at most once, and all failures end in a valid plan or explicit clarification state. Run existing LLM fallback tests with no API key.

#### Expected Output / Result

When a missing or regenerated skill is needed, the selected model produces a structured teaching skill that passes validation before compilation. A model outage behaves like a normal offline MVP run. The session records only safe skill metadata and lifecycle, never hidden reasoning or raw model output.

#### Testing Script

##### Act 01: Route STEM Generation

Mock a missing `深度學習` skill and set the STEM model override.

Pass condition: the generator receives the STEM route and returns only after skill validation succeeds.

##### Act 02: Recover from Invalid Output

Return an invalid skill on the first generation call and a valid skill on the second.

Pass condition: exactly one retry occurs and the compiled plan is valid.

##### Act 03: Operate Without an API Key

Unset `OPENROUTER_API_KEY` and request an existing catalog skill.

Pass condition: the catalog skill compiles offline and no external call is attempted.

#### Gate to Enter the Next Phase

```bash
cd misc/PELICAN_mvp
python -m pytest tests/test_llm.py tests/test_skill_generator.py tests/test_planner.py tests/test_skill_compiler.py -q
python -m pytest tests/test_models.py tests/test_state_store.py tests/test_engine.py -q
git diff --check
```

All tests must pass with credentials absent. Mock assertions must prove route and retry bounds. Retain logs/test output proving no raw model content is emitted. Fix failures before interactive engine changes.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): add validated domain skill generation
```

Inspect status, stage only Phase 3 paths/hunks, run cached diff checks and stat review, commit, and confirm with `git show --stat --oneline --summary HEAD`.

#### Phase 3 Implementation Status

Completed on 2026-07-20 in commit `0b3ee86 feat(pelican): add validated domain skill generation`.

Verification evidence retained from the phase gate:

```bash
cd misc/PELICAN_mvp
python -m pytest tests/test_llm.py tests/test_skill_generator.py tests/test_planner.py tests/test_skill_compiler.py -q
# 24 passed

python -m pytest tests/test_models.py tests/test_state_store.py tests/test_engine.py -q
# 26 passed

git diff --check
# passed with no whitespace errors
```

The implementation follows the Phase 3 boundary: it adds category-aware model route selection, structured domain-skill generation, bounded validation retry, planner compilation from validated skills only, safe skill metadata persistence, and offline/mock tests. It preserves deterministic catalog behavior without credentials and does not begin calibration-first engine changes.

### Phase 4: Calibration-First Teaching Runtime and Educational Evaluation

#### Problem

The current engine changes from onboarding to diagnosis after one topic message. It has no separate goal/level calibration, does not recognize scope mismatch as a control signal, and treats `不知道` as a reason to advance to another diagnostic node. This makes the learner experience feel random and can increase cognitive load. The existing EDF policy is computed after evidence but is not yet connected to domain-specific remediation.

#### Assumptions

- Existing fixture curriculum behavior is frozen and remains outside the new domain-skill onboarding path.
- Intake may require multiple turns, but the API response shape should remain backward-compatible by returning the existing `TurnOutcome` plus safe learning metadata.
- Initial success is measured by behavioral acceptance criteria, not model benchmark scores or a claim of universal teaching quality.

#### Solution

Make onboarding a small state machine: collect topic, ask the learner's goal, ask a lightweight self-assessment or prior-experience signal, then compile the session tree. Present a single low-load calibration question from the skill's calibration policy. Interpret `too_detailed`/`too_difficult` as scope mismatch and re-calibrate or move to the prerequisite; interpret `unknown` as a scaffold request and teach/diagnose the declared prerequisite; interpret `too_easy` as an acceleration request; and route project/assessment goals to their respective skill path. Only after this contract is satisfied may successor-first diagnosis proceed.

Extend local memory using the AREQA boundary. Store a bounded, prompt-safe direct evidence record containing source, kind, text, topic/node context, signal, and remediation intent. Keep EDF learner state, pedagogical strategy, and model-generated interpretations in `EdfSnapshot`/session metadata and never promote them to durable user profile memory. Add domain teaching moves to tutoring strategy selection so EDF policy chooses a domain-approved action rather than an arbitrary next question.

Define acceptance metrics: broad topics do not start with an advanced probe; intent and level are collected; same input yields a stable route; mismatch/unknown responses trigger remediation; each diagnostic maps to one concept; prerequisite relationships are valid; and memory provenance is preserved. These are the Phase 4 MVP success criteria and should be captured in deterministic tests and a manual script.

#### Implementation

> Context: Add Google-style docstrings to every new or materially changed public module, class, and function. Document each onboarding transition, why mismatch is not mastery evidence, how scaffold selection follows the skill prerequisite map, and the separation between direct evidence and EDF inference. Add rationale comments only around transition precedence and fallback handling. Emit safe structured events for intake progress, scope mismatch, scaffold selection, route compilation, remediation, and phase transitions; never log raw learner text, prompts, answers, or generated teaching content.

1. [x] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py` to implement calibration-first onboarding and skill-aware remediation.
   - [x] Add explicit intake progress handling for topic, goal/intent, and level/prior experience.
   - [x] Prevent `_present_next_diagnostic()` from running until the profile-aware plan is compiled.
   - [x] Add precedence for scope mismatch and inability before normal successor-first advancement.
   - [x] Preserve fixture curriculum paths and existing CLI commands.
2. [x] Modify `misc/PELICAN_mvp/pelican_mvp/diagnosis.py` and `tutoring.py` to expose skill remediation signals and domain teaching moves without changing fixture classifications.
3. [x] Modify `misc/PELICAN_mvp/pelican_mvp/learning_memory.py` and `models.py` to persist bounded direct-evidence records with `source`, `kind`, `prompt_safe`, `cold_export_eligible=False`, and learning context; keep EDF inference separate.
4. [x] Modify `misc/PELICAN_mvp/pelican_mvp/server.py` to expose safe intake progress, skill metadata, and remediation state in the existing learning payload.
5. [x] Update `misc/PELICAN_mvp/README.md` with the calibration-first flow, supported categories, offline behavior, legal-education boundary, and lifecycle comments.
6. [x] Extend `misc/PELICAN_mvp/tests/test_engine.py`, `test_learning_memory.py`, `test_server.py`, and `test_e2e.py`; add `misc/PELICAN_mvp/tests/test_pedagogical_flow.py` for acceptance behavior.
   - [x] Cover `深度學習` -> goal/level intake -> foundation-first diagnostic.
   - [x] Cover `這太細了吧` -> scope mismatch and lower-level recalibration.
   - [x] Cover `不知道` -> prerequisite scaffold, not unrelated next-node advancement.
   - [x] Cover `太簡單了`, project, assessment, unknown domain, legal education disclaimer, persistence/restart, and evidence privacy.

#### Expected File Tree After Phase 4

The tree is cumulative from all prior phases.

```text
misc/PELICAN_mvp/
├── README.md                         [modified]
├── pelican_mvp/
│   ├── diagnosis.py                  [modified]
│   ├── engine.py                     [modified]
│   ├── learning_memory.py            [modified]
│   ├── models.py                     [modified]
│   ├── server.py                     [modified]
│   └── tutoring.py                   [modified]
└── tests/
    ├── test_engine.py                [modified]
    ├── test_e2e.py                   [modified]
    ├── test_learning_memory.py       [modified]
    ├── test_pedagogical_flow.py      [new]
    └── test_server.py                [modified]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py` to collect intent/level before plan compilation and apply skill remediation for mismatch and inability.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/diagnosis.py` and `misc/PELICAN_mvp/pelican_mvp/tutoring.py` to consume skill policy while preserving fixture behavior.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/learning_memory.py` and `misc/PELICAN_mvp/pelican_mvp/models.py` to implement AREQA-aligned direct evidence records and bounded context.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/server.py` to serialize safe intake, skill, and remediation metadata without user text.
5. [ ] Modify `misc/PELICAN_mvp/README.md` to document the supported domain-skill runtime and its experimental boundaries.
6. [ ] Extend `misc/PELICAN_mvp/tests/test_engine.py`, `test_learning_memory.py`, `test_server.py`, and `test_e2e.py`; create `misc/PELICAN_mvp/tests/test_pedagogical_flow.py` for the acceptance criteria and regression cases.

#### Test Plan

Run unit tests for intake transitions, mismatch classification, prerequisite scaffolding, memory provenance, EDF separation, and deterministic compilation. Run API tests for response compatibility and safe metadata. Run the Playwright E2E test only when its dependency is installed; otherwise record the missing dependency as a test gap rather than treating it as passed. The manual script must replay the reported deep-learning conversation and demonstrate a foundation-first recovery.

#### Expected Output / Result

The first response to `深度學習` asks a useful calibration question instead of MLP parameter counting. A learner who says the question is too detailed is moved to a lower abstraction level; a learner who says `不知道` receives a prerequisite scaffold and an understandable next step. The resulting knowledge tree is stable, domain-appropriate, and backed by a validated skill. Direct user evidence is bounded and source-tagged; EDF decisions influence teaching but do not become user profile facts.

#### Testing Script

##### Act 01: Complete Calibration Before Diagnosis

Create a fresh rule-mode learner, send `深度學習`, then answer the goal and prior-experience prompts with `想理解原理` and `完全沒有基礎`.

Pass condition: the first diagnostic is a validated foundation concept and the persisted phase/skill metadata show completed intake.

##### Act 02: Handle Scope Mismatch

At the first diagnostic, send `這太細了吧，我不知道`.

Pass condition: the engine records a mismatch/inability signal, presents a lower-level explanation or prerequisite scaffold, and does not advance to an unrelated advanced node.

##### Act 03: Preserve Evidence Provenance

Inspect persisted state after the mismatch response and EDF evaluation.

Pass condition: the user response is stored as direct evidence with prompt-safe/source metadata, while learner state and pedagogical strategy remain separate EDF metadata.

##### Act 04: Preserve Fixture Compatibility

Start the existing `cnn` fixture and answer its known test sequence.

Pass condition: the fixture still reaches tutoring/completion with its original node IDs and rule behavior.

##### Act 05: Reject Legal Advice Framing

Start a legal-knowledge session and request a personalized legal decision.

Pass condition: the skill/runtime keeps the educational-only boundary and does not present the response as legal advice.

#### Gate to Enter the Next Phase

```bash
cd misc/PELICAN_mvp
python -m pytest -q
python -m pytest tests/test_pedagogical_flow.py tests/test_engine.py tests/test_learning_memory.py tests/test_server.py -q
python -m pelican_mvp --help
git diff --check
```

The full suite and focused acceptance suite must pass. If Playwright is unavailable, run all non-E2E tests and explicitly record the missing dependency and manual browser verification as unresolved; do not claim full acceptance. Verify no file under `backend/` changed, inspect structured log captures for redaction, and retain the deep-learning manual transcript result.

#### Phase Commit

Commit exactly one coherent phase commit after the gate passes:

```text
feat(pelican): add calibration-first pedagogical runtime
```

Inspect `git status --short` and preserve unrelated user changes. Stage only Phase 4 paths/hunks, run `git diff --cached --check` and review `git diff --cached --stat`, create one commit, and confirm with `git show --stat --oneline --summary HEAD`. Do not amend or push unrelated work.

#### Phase 4 Implementation Status

Completed on 2026-07-20 in commit `bf3d1cf feat(pelican): add calibration-first pedagogical runtime`.

Verification evidence retained from the phase gate:

```bash
cd misc/PELICAN_mvp
python -m pytest -q
# 98 passed, 1 warning

python -m pytest tests/test_pedagogical_flow.py tests/test_engine.py tests/test_learning_memory.py tests/test_server.py -q
# 26 passed, 1 warning

python -m pelican_mvp --help
# argparse help printed successfully

git diff --check
# passed with no whitespace errors
```

Boundary verification:

```bash
git diff --name-only -- backend frontend
# no output
```

Manual deep-learning replay:

```text
AI: 歡迎！你想學什麼？
User: 深度學習
AI: 你這次比較想怎麼學？
User: 想理解原理
AI: 你目前的基礎大概在哪裡？
User: 完全沒有基礎
AI: 太好了，我們來一起學習「深度學習」吧！
User: 這太細了吧，我不知道
AI: 收到，剛才那題對目前起點太細了。我們先退回一層...
phase=diagnosis, node=math_intuition, signal=too_detailed, skill=deep_learning
```

The implementation follows the Phase 4 boundary: it adds calibration-first onboarding, skill-aware mismatch/scaffold/acceleration handling, safe learning metadata exposure, AREQA-aligned bounded direct evidence records, README documentation, and acceptance coverage. Fixture curricula still bypass onboarding when explicitly selected.

### Cross-Phase Regression and Final Acceptance

Run the complete MVP regression from the repository root:

```bash
cd misc/PELICAN_mvp
python -m pytest -q
python -m pelican_mvp --help
git diff --check
```

Focused commands that must also be retained are:

```bash
python -m pytest tests/test_domain_skill.py tests/test_skill_validator.py tests/test_skill_loader.py tests/test_skill_compiler.py -q
python -m pytest tests/test_pedagogical_flow.py tests/test_engine.py tests/test_learning_memory.py tests/test_server.py -q
```

Final manual acceptance must replay the reported `深度學習` scenario and confirm: broad intake first, explicit goal/level calibration, foundation-first tree, no random MLP-first probe, remediation for `太細了` and `不知道`, stable route across repeated fresh sessions, and direct-evidence-only memory behavior. Repeat one fixture `cnn` scenario to prove the compatibility boundary.

Acceptance outcomes:

- A domain skill is validated before it can compile a session plan.
- The first deep-learning route is pedagogically appropriate for an uncalibrated beginner.
- Intent-specific routes exist for conceptual, implementation, project, and assessment goals.
- STEM and humanities/business/language routes use configurable model slugs from their agreed category mapping.
- Model failure falls back to a valid deterministic route.
- User evidence and EDF/model inference remain separate and logs are redacted.
- No production `backend/` file is modified.

Remaining risks and mitigations:

- Model availability, pricing, and exact route slugs may change; keep them environment-configurable and verify against the local model docs at deployment time.
- A single deep-learning seed skill does not prove universal domain teaching; expand skills only after replay-based evaluation.
- Rule-based mismatch detection may miss indirect language; retain an optional LLM classifier behind a fail-safe deterministic fallback.
- Playwright dependency may be absent in the current environment; keep API/unit coverage complete and record browser verification separately.
- Legal education requires jurisdiction and date context; continue to prohibit personalized legal advice in both skill policy and runtime responses.

Before declaring completion, run `git status --short` and review ordered `git log --oneline` to prove all four phase commits exist and no planned change remains uncommitted. Resolve or explicitly record any deployment decision about API keys, model budget, skill persistence, and future approval workflow.
