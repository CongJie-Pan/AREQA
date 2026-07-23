# Agentic PELICAN Agent Executor Implementation Plan

The current MVP already records agent roles and bounded proposals, but most roles are still labels emitted by `PelicanEngine` around service/helper calls. The target is to align the implementation with the methodology figure: each agent owns a bounded subtask, produces a proposal artifact, and lets the learning-system pipeline validate/adopt/reject the proposal. The phase order first stabilizes contracts and observability, then extracts `SkillAgent` because skill construction is the most important domain-generalization boundary, and then migrates the remaining agents without breaking the existing manual experiment flow.

### Phase 1: Define the Agent Proposal Runtime Contract

#### Problem

The code has `AgentRole` and `AgentProposal`, but there is no explicit executor contract that separates an agent's proposed artifact from the engine's validated state mutation. This makes the UI look agentic while the backend remains mostly engine-orchestrated. The observable target state is a documented and testable agent contract that every later agent can implement consistently.

#### Assumptions

- `PelicanEngine` remains the final state owner and may reject any agent proposal.
- Existing session JSON records must continue to load.
- Agent artifacts must never include raw learner text, raw prompts, provider response bodies, credentials, or hidden reasoning.
- If this assumption is false and raw artifacts are required for research, that must become an explicit opt-in export mode outside this plan.

#### Solution

Introduce a small internal agent runtime contract with typed inputs, outputs, validation status, safe artifact references, and structured-log semantics. The contract should be independent from LLM availability: rule/catalog/cache/fallback paths are also agent proposals, but their source and fallback status must be explicit.

#### Implementation

> Context: Add Google-style docstrings for every new public module, class, and function. Document why `PelicanEngine` keeps final mutation ownership, why proposal artifacts are bounded, and which structured logs are privacy-safe. Inline comments should appear only at policy/fallback boundaries where future maintainers could accidentally persist raw content.

Add a proposed `pelican_mvp/agents/` package with shared types and helpers only. Do not migrate existing stage logic in this phase.

#### Expected File Tree After Phase 1

This tree is cumulative for Phase 1 only.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── agents/
│   │   ├── __init__.py                         [new]
│   │   ├── base.py                             [new]
│   │   └── artifacts.py                        [new]
│   ├── models.py                               [modified]
│   └── observability.py                        [modified]
└── tests/
    └── test_agent_contract.py                  [new]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/base.py`.
   - [ ] Add proposed `AgentExecutionContext` with safe fields: `learner_id`, `turn_id`, `cycle_id`, `phase`, `mode`, `node_id`, `skill_id`, `edf_state`, `edf_policy`, `recent_safe_signals`.
   - [ ] Add proposed `AgentExecutionResult` with safe fields: `role`, `stage`, `artifact_type`, `artifact_ref`, `validation_status`, `reason_code`, `display_summary`, `pedagogical_move`, `final_message_preview`.
   - [ ] Add proposed `BaseAgent.propose()` protocol method without implementing concrete logic.
2. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/artifacts.py`.
   - [ ] Add proposed `safe_artifact_ref()` helper that builds `MethodologyRef` without raw payload content.
   - [ ] Add proposed `bound_agent_text()` helper for summary/preview fields.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/models.py`.
   - [ ] Extend `AgentProposal` only if missing fields are needed by `AgentExecutionResult`; keep defaults so legacy session records load.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/observability.py`.
   - [ ] Add safe allow-list fields needed by agent executor logs, such as `agent_stage`, `artifact_type`, `proposal_source`, and `agent_status`.
5. [ ] Add `misc/PELICAN_mvp/tests/test_agent_contract.py`.
   - [ ] Test that proposed contract serialization excludes raw learner text.
   - [ ] Test that malformed or empty display fields are bounded.

#### Test Plan

Run focused model/contract tests and existing model persistence tests:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_agent_contract.py tests/test_models.py -q
python -m compileall -q pelican_mvp
```

#### Expected Output / Result

The repository has a concrete internal agent contract. No runtime behavior changes yet. Existing UI/API behavior remains unchanged, but future phases can migrate stages onto the contract.

#### Testing Script

##### Act 01: Contract Bounds Safe Metadata

Create an `AgentExecutionResult` containing a fake raw learner answer in an unsupported field.

Pass condition: serialization and proposal conversion do not expose the raw learner answer.

##### Act 02: Legacy Proposal Still Loads

Load a session/proposal dictionary without new fields.

Pass condition: `AgentProposal.from_dict()` succeeds and missing fields default safely.

#### Gate to Enter the Next Phase

Required commands:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_agent_contract.py tests/test_models.py -q
python -m compileall -q pelican_mvp
```

Success condition: all commands pass. Retain terminal output in the implementation notes. If the gate fails, fix contract/schema compatibility before starting Phase 2.

#### Phase Commit

Commit message:

```bash
feat(pelican): define agent executor contract
```

Staging scope:

```bash
git status --short
git add misc/PELICAN_mvp/pelican_mvp/agents/__init__.py \
        misc/PELICAN_mvp/pelican_mvp/agents/base.py \
        misc/PELICAN_mvp/pelican_mvp/agents/artifacts.py \
        misc/PELICAN_mvp/pelican_mvp/models.py \
        misc/PELICAN_mvp/pelican_mvp/observability.py \
        misc/PELICAN_mvp/tests/test_agent_contract.py
git diff --cached --check
git diff --cached --stat
git commit -m "feat(pelican): define agent executor contract"
git show --stat --oneline --summary HEAD
```

Do not stage unrelated experiment artifacts under `docs/2026_07_23_experiment/`.

### Phase 2: Extract SkillAgent as the First Real Agent Executor

#### Problem

Skill construction currently happens through `LearningPlanner` and `DomainSkillGenerator`, then `PelicanEngine` records `AgentRole.SKILL_AGENT` proposal metadata. This is not a true Skill Agent boundary. The observable target state is that Skill Agent receives the scoped objective/profile, proposes a skill artifact or fallback artifact, records attempts, and returns a validated proposal to the engine.

#### Assumptions

- Existing catalog/cache/runtime/generic fallback ordering is correct and should be preserved.
- `DomainSkillGenerator` may remain the low-level generation service, but `SkillAgent` owns the stage-level proposal semantics.
- `LearningPlanner` should compile only a validated skill proposal, not decide agent proposal status itself.
- If preserving this ordering proves incompatible, the phase must stop and document which fallback behavior changes.

#### Solution

Create `SkillAgent` as an executor that wraps domain routing, catalog lookup, cache lookup, LLM generation/repair, validation, and fallback selection into one bounded `skill_generation` proposal. `PelicanEngine` should call `SkillAgent.propose_skill()` during onboarding completion, then compile the accepted skill into `LearningPlanSnapshot`.

#### Implementation

> Context: Document the Skill Agent ownership boundary: it owns skill proposal generation and validation evidence, while `PelicanEngine` owns session state mutation and methodology event adoption. Add Google-style docstrings to new `SkillAgent`, proposal/result types, and changed planner methods. Document fallback semantics and structured logs: `pelican_skill_agent_started`, `pelican_skill_agent_attempt_recorded`, `pelican_skill_agent_proposal_validated`, and `pelican_skill_agent_fallback_used`.

Use existing `DomainSkillGenerator.generate_with_result()` internally at first to keep risk low. Do not rewrite the LLM prompt in this phase unless tests prove the existing path cannot expose the required proposal artifact.

#### Expected File Tree After Phase 2

This tree is cumulative from Phase 1.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── agents/
│   │   ├── skill_agent.py                     [new]
│   │   └── base.py                            [modified]
│   ├── domain_catalog.py                      [modified]
│   ├── engine.py                              [modified]
│   ├── planner.py                             [modified]
│   ├── server.py                              [modified]
│   └── skill_generator.py                     [modified]
└── tests/
    ├── test_domain_skill.py                   [modified]
    ├── test_skill_agent.py                    [new]
    ├── test_pedagogical_flow.py               [modified]
    └── test_server.py                         [modified]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/skill_agent.py`.
   - [ ] Add proposed `SkillAgentInput` carrying `LearnerIntakeProfile`, safe topic, domain route, and force-regenerate flag.
   - [ ] Add proposed `SkillAgentProposal` carrying `DomainSkill`, route, attempts, fallback flag, final reason code, and safe display summary.
   - [ ] Add `SkillAgent.propose_skill()` that wraps `DomainSkillGenerator.generate_with_result()`.
2. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/planner.py`.
   - [ ] Split `LearningPlanner.create_plan_for_profile()` into proposed `compile_validated_skill()` plus fallback-only compatibility method.
   - [ ] Remove direct ownership of `last_skill_generation_result` after `PelicanEngine` migrates to `SkillAgent`.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py`.
   - [ ] In `_handle_onboarding()`, replace direct `self.planner.create_plan_for_profile(profile)` skill generation with `self.skill_agent.propose_skill()`.
   - [ ] Record `AgentRole.SKILL_AGENT` proposals from `SkillAgentProposal.attempts`.
   - [ ] Compile only accepted or fallback skill proposals into `LearningPlanSnapshot`.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/domain_catalog.py`.
   - [ ] Add or verify humanities routing coverage for the manual non-hardcoded scenario: `中國春秋時期歷史`, `春秋時期`, `春秋五霸`, `諸侯爭霸`, `周王室`, `尊王攘夷`, `禮崩樂壞`, and `戰國`.
   - [ ] Keep route output safe and category-level; do not hardcode a Spring-and-Autumn lesson plan in the router.
5. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/server.py`.
   - [ ] Ensure `skill_artifact_summary` exposes `proposal_source`, `used_fallback`, and `final_reason_code` when available.
6. [ ] Add `misc/PELICAN_mvp/tests/test_skill_agent.py`.
   - [ ] Test catalog skill proposal for `深度學習`.
   - [ ] Test `中國春秋時期歷史` in LLM mode with a fake humanities skill payload and assert the accepted skill contains history-specific concept labels such as `周王室權威`, `分封秩序`, `諸侯爭霸`, or equivalent non-STEM historical terms.
   - [ ] Test offline known-domain generic fallback is marked `fallback_used`.
   - [ ] Test unknown-domain proposal fails closed or requests clarification without silently compiling a fake expert skill.
7. [ ] Modify `misc/PELICAN_mvp/tests/test_domain_skill.py`.
   - [ ] Assert the Spring-and-Autumn aliases route to `DomainCategory.HUMANITIES`, not `UNKNOWN` or `STEM`.
8. [ ] Modify `misc/PELICAN_mvp/tests/test_pedagogical_flow.py`.
   - [ ] Assert onboarding completion records Skill Agent proposal before Skill Construction methodology event.
   - [ ] Add a Spring-and-Autumn manual-flow regression using a fake accepted humanities skill and assert the first diagnostic is historical-context-first, not a deep-learning or STEM prompt.
9. [ ] Modify `misc/PELICAN_mvp/tests/test_server.py`.
   - [ ] Assert API metadata shows skill proposal source/fallback status safely.
   - [ ] Assert API `skill_artifact_summary` for `中國春秋時期歷史` exposes humanities domain, history concept path, current diagnostic target, and no deep-learning/STEM labels.

#### Test Plan

Focused tests:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_domain_skill.py tests/test_skill_agent.py tests/test_pedagogical_flow.py tests/test_server.py -q
python -m compileall -q pelican_mvp
```

Boundary cases:

- catalog hit: accepted proposal;
- runtime cache hit: accepted proposal;
- Spring-and-Autumn humanities topic: accepted runtime/cache skill or explicitly labeled humanities fallback, never deep-learning/STEM content;
- LLM unavailable for known domain: generic fallback proposal;
- unknown domain: clarification/fallback behavior is explicit;
- invalid generated skill: rejected attempt followed by repair/fallback metadata.

#### Expected Output / Result

Skill construction is no longer only a helper call labeled afterward. The Skill Agent owns the stage proposal, attempts, validation result, route, and fallback reason. The engine adopts the proposal and compiles it.

#### Testing Script

##### Act 01: Catalog Skill Agent Proposal

Input topic `深度學習`, goal `想理解原理`, level `完全沒有基礎`.

Pass condition: latest Skill Agent proposal is accepted with source `catalog`, and compiled plan contains the expected foundation path.

##### Act 02: Spring-and-Autumn Runtime Skill Proposal

Input topic `中國春秋時期歷史`, goal `想理解春秋時期的政治秩序和諸侯爭霸脈絡`, level `只有大概聽過春秋五霸，沒有系統學過`.

Pass condition: Skill Agent proposal is accepted from `runtime_generated` or `runtime_cache`, the compiled concept path contains history-specific Spring-and-Autumn concepts, and no deep-learning/STEM concept labels appear.

##### Act 03: Offline Known Domain Fallback

Disable LLM config and input a known humanities topic without catalog coverage.

Pass condition: Skill Agent proposal is `fallback_used`, source is `generic:humanities`, and no legacy unlabeled plan is presented as accepted generation.

##### Act 04: Unknown Domain Fails Closed

Input a topic not matched by router aliases.

Pass condition: the engine requests clarification or records explicit fallback reason; it does not display a domain-specific expert skill that was never validated.

#### Gate to Enter the Next Phase

Required commands:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_domain_skill.py tests/test_skill_agent.py tests/test_pedagogical_flow.py tests/test_server.py -q
python -m compileall -q pelican_mvp
```

Success condition: every Skill Agent path records proposal source/status/reason safely, and the Spring-and-Autumn manual scenario produces either an accepted history-specific skill or an explicitly labeled fallback. If any fallback is ambiguous, or any Spring-and-Autumn output contains deep-learning/STEM content, do not proceed.

#### Phase Commit

Commit message:

```bash
feat(pelican): extract skill agent executor
```

Staging scope:

```bash
git status --short
git add misc/PELICAN_mvp/pelican_mvp/agents/skill_agent.py \
        misc/PELICAN_mvp/pelican_mvp/agents/base.py \
        misc/PELICAN_mvp/pelican_mvp/domain_catalog.py \
        misc/PELICAN_mvp/pelican_mvp/engine.py \
        misc/PELICAN_mvp/pelican_mvp/planner.py \
        misc/PELICAN_mvp/pelican_mvp/server.py \
        misc/PELICAN_mvp/pelican_mvp/skill_generator.py \
        misc/PELICAN_mvp/tests/test_domain_skill.py \
        misc/PELICAN_mvp/tests/test_skill_agent.py \
        misc/PELICAN_mvp/tests/test_pedagogical_flow.py \
        misc/PELICAN_mvp/tests/test_server.py
git diff --cached --check
git diff --cached --stat
git commit -m "feat(pelican): extract skill agent executor"
git show --stat --oneline --summary HEAD
```

### Phase 3: Extract Intake, Diagnosis, State, and Policy Agents

#### Problem

After Skill Agent extraction, the remaining methodology stages still mostly run as engine logic with agent labels. The figure requires each stage to have a responsible agent proposal before the pipeline adopts it. The target state is explicit agent executors for intake interpretation, diagnostic task selection, state update proposal, and EDF strategy recommendation.

#### Assumptions

- The deterministic rule behavior must stay available for tests and offline demo.
- State mutation still belongs to `PelicanEngine`; `StateAgent` proposes state deltas but does not directly update `SessionState`.
- `PolicyAgent` may wrap the current `EdfSimulator` initially.
- If a new agent creates a different output than the current engine, tests must decide whether the difference is intended before accepting it.

#### Solution

Extract four small agents with narrow ownership:

- `IntakeAgent`: topic/goal/level interpretation proposal.
- `DiagnosisAgent`: next diagnostic node/task proposal.
- `StateAgent`: knowledge-state delta proposal.
- `PolicyAgent`: EDF/GUM strategy proposal.

Each agent returns an `AgentExecutionResult`; the engine validates and applies the result.

#### Implementation

> Context: Each new agent must document its input/output ownership, what it is not allowed to mutate, and how it fails closed. Add Google-style docstrings for every public class/function. Document structured logs for proposal started/accepted/rejected/fallback. Inline comments should explain why the engine validates before mutation and why raw learner text remains outside proposal records.

Migrate one agent at a time inside this phase, keeping tests green after each migration.

#### Expected File Tree After Phase 3

This tree is cumulative from Phase 2.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── agents/
│   │   ├── intake_agent.py                    [new]
│   │   ├── diagnosis_agent.py                 [new]
│   │   ├── state_agent.py                     [new]
│   │   └── policy_agent.py                    [new]
│   ├── engine.py                              [modified]
│   ├── diagnosis.py                           [modified]
│   ├── edf_simulator.py                       [modified]
│   └── learning_memory.py                     [modified]
└── tests/
    ├── test_intake_agent.py                   [new]
    ├── test_diagnosis_agent.py                [new]
    ├── test_state_agent.py                    [new]
    ├── test_policy_agent.py                   [new]
    └── test_engine.py                         [modified]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/intake_agent.py`.
   - [ ] Add proposed `IntakeAgent.propose_topic()`, `propose_goal()`, and `propose_level()` using existing semantic classifier/rules.
   - [ ] Update `PelicanEngine._handle_onboarding()` to adopt intake proposals.
2. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/diagnosis_agent.py`.
   - [ ] Add proposed `DiagnosisAgent.propose_next_diagnostic()` wrapping `next_diagnostic_node()` and optional `verified_diagnostic()`.
   - [ ] Update `PelicanEngine._present_next_diagnostic()` to use the proposal.
3. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/state_agent.py`.
   - [ ] Add proposed `StateAgent.propose_diagnostic_update()` and `propose_practice_update()` returning bounded state-delta metadata.
   - [ ] Update `PelicanEngine._handle_diagnostic()` and `_handle_tutoring()` to apply validated deltas.
4. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/policy_agent.py`.
   - [ ] Add proposed `PolicyAgent.propose_strategy()` wrapping `EdfSimulator.evaluate()` and `select_strategy()`.
   - [ ] Update `_refresh_learning_context()` and tutoring paths to adopt policy proposals.
5. [ ] Add tests under `misc/PELICAN_mvp/tests/`.
   - [ ] `test_intake_agent.py`: topic revision, goal interpretation, level interpretation.
   - [ ] `test_diagnosis_agent.py`: skill-locked diagnostic and LLM diagnostic fallback.
   - [ ] `test_state_agent.py`: correct/incorrect/unknown state delta without raw answer leakage.
   - [ ] `test_policy_agent.py`: current-turn evidence changes strategy.
   - [ ] `test_engine.py`: methodology order still matches six core stages.

#### Test Plan

Run focused tests plus existing engine regression:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_intake_agent.py tests/test_diagnosis_agent.py tests/test_state_agent.py tests/test_policy_agent.py tests/test_engine.py -q
python -m compileall -q pelican_mvp
```

#### Expected Output / Result

Methodology stages now have concrete agent executors for their proposals. Existing UI still shows the same six-stage pipeline, but proposal provenance becomes more defensible.

#### Testing Script

##### Act 01: Intake Agent Owns Goal Framing

Input `中國春秋時期歷史`, then `想理解春秋時期的政治秩序和諸侯爭霸脈絡`, then `只有大概聽過春秋五霸，沒有系統學過`.

Pass condition: each onboarding turn records an Intake Agent proposal before profile mutation.

##### Act 02: Diagnosis Agent Owns Diagnostic Task

Complete onboarding for `中國春秋時期歷史`.

Pass condition: Diagnosis Agent proposal references the selected node before the diagnostic prompt is shown.

##### Act 03: State and Policy Agents Own Evidence Adoption

Answer the first diagnostic correctly.

Pass condition: State Agent proposal appears before state update, and Policy Agent proposal appears after GUM/evidence refresh.

#### Gate to Enter the Next Phase

Required commands:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_intake_agent.py tests/test_diagnosis_agent.py tests/test_state_agent.py tests/test_policy_agent.py tests/test_engine.py -q
python -m compileall -q pelican_mvp
```

Success condition: every migrated stage has a real agent proposal and no raw learner payload leaks into proposals/logs. If stage ordering changes, update tests only after confirming the paper methodology still matches.

#### Phase Commit

Commit message:

```bash
feat(pelican): extract methodology stage agents
```

Staging scope:

```bash
git status --short
git add misc/PELICAN_mvp/pelican_mvp/agents/intake_agent.py \
        misc/PELICAN_mvp/pelican_mvp/agents/diagnosis_agent.py \
        misc/PELICAN_mvp/pelican_mvp/agents/state_agent.py \
        misc/PELICAN_mvp/pelican_mvp/agents/policy_agent.py \
        misc/PELICAN_mvp/pelican_mvp/engine.py \
        misc/PELICAN_mvp/pelican_mvp/diagnosis.py \
        misc/PELICAN_mvp/pelican_mvp/edf_simulator.py \
        misc/PELICAN_mvp/pelican_mvp/learning_memory.py \
        misc/PELICAN_mvp/tests/test_intake_agent.py \
        misc/PELICAN_mvp/tests/test_diagnosis_agent.py \
        misc/PELICAN_mvp/tests/test_state_agent.py \
        misc/PELICAN_mvp/tests/test_policy_agent.py \
        misc/PELICAN_mvp/tests/test_engine.py
git diff --cached --check
git diff --cached --stat
git commit -m "feat(pelican): extract methodology stage agents"
git show --stat --oneline --summary HEAD
```

### Phase 4: Split Fast Tutor Agent and Slow Simulator Agent

#### Problem

The current tutor proposal path has `FAST_TUTOR_AGENT` and `SLOW_SIMULATOR_AGENT` roles, but the slow route is mostly a strategy label, not a separate simulator-style proposal path. The target state is that fast and slow tutor agents have distinct proposal logic, validation, fallback, and trace metadata.

#### Assumptions

- The final learner-facing message still goes through one validator before display.
- Fast route should prioritize low-latency scaffold/confirmation.
- Slow route should be selected only for repeated failures, fragile state, or high uncertainty.
- If LLM is unavailable, slow route must degrade to deterministic fallback and mark `fallback_used`.

#### Solution

Create two tutor agents:

- `FastTutorAgent`: produces concise one-step guidance.
- `SlowSimulatorAgent`: produces deeper simulation/planning proposals for repeated or complex learner difficulty.

Both agents return bounded tutor proposals and use the existing validation/fallback code.

#### Implementation

> Context: Tutor agents produce learner-facing candidate content, so docstrings must clearly define the privacy and safety boundary. Document why raw prompts/model output are not persisted, how validation rejects off-node/too-long/strategy-mismatched proposals, and which safe fields are logged. Inline comments should explain fallback branches and slow-route selection only.

Refactor the existing `_tutor_message()`, `_validate_tutor_proposal()`, and `_fallback_tutor_proposal()` logic into reusable tutor-agent modules.

#### Expected File Tree After Phase 4

This tree is cumulative from Phase 3.

```text
misc/PELICAN_mvp/
├── pelican_mvp/
│   ├── agents/
│   │   ├── fast_tutor_agent.py                [new]
│   │   └── slow_simulator_agent.py            [new]
│   ├── engine.py                              [modified]
│   ├── llm.py                                 [modified]
│   └── tutoring.py                            [modified]
└── tests/
    ├── test_tutor_agents.py                   [new]
    ├── test_pedagogical_flow.py               [modified]
    └── test_llm.py                            [modified]
```

#### Work List

1. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/fast_tutor_agent.py`.
   - [ ] Add proposed `FastTutorAgent.propose_response()` using current bounded tutor proposal fields.
2. [ ] Create `misc/PELICAN_mvp/pelican_mvp/agents/slow_simulator_agent.py`.
   - [ ] Add proposed `SlowSimulatorAgent.propose_response()` with slow-route metadata and deterministic fallback.
3. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/engine.py`.
   - [ ] Replace `_tutor_message()` implementation with calls to Fast/Slow tutor agents.
   - [ ] Keep `_validate_tutor_proposal()` only if it remains engine-owned; otherwise move it into a shared tutor validation helper.
4. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/llm.py`.
   - [ ] Add explicit `slow_tutor_proposal()` only if slow route needs different prompt constraints.
5. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/tutoring.py`.
   - [ ] Ensure `select_strategy()` exposes a stable reason code for fast/slow routing.
6. [ ] Add `misc/PELICAN_mvp/tests/test_tutor_agents.py`.
   - [ ] Test fast proposal for `unknown`.
   - [ ] Test slow proposal after repeated failures.
   - [ ] Test invalid LLM proposal falls back safely.
7. [ ] Modify `misc/PELICAN_mvp/tests/test_pedagogical_flow.py`.
   - [ ] Assert `unknown` and `too_detailed` still produce distinct messages and proposal moves.
8. [ ] Modify `misc/PELICAN_mvp/tests/test_llm.py`.
   - [ ] Assert tutor proposal payloads remain bounded and structured.

#### Test Plan

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_tutor_agents.py tests/test_pedagogical_flow.py tests/test_llm.py -q
python -m compileall -q pelican_mvp
```

#### Expected Output / Result

Fast and slow tutor routes become real agent executors with distinct traceable behavior. UI/export can distinguish fast response from slow simulation rather than merely showing a role label.

#### Testing Script

##### Act 01: Fast Tutor Scaffold

After reaching a foundation diagnostic, input `我不知道`.

Pass condition: Fast or Slow tutor selection is justified by safe reason code, and proposal move is `scaffold`.

##### Act 02: Slow Simulator Route

Cause repeated incorrect/inability responses on the same node.

Pass condition: Slow Simulator Agent proposal appears with slow-route reason code and bounded final message preview.

##### Act 03: Invalid Proposal Fallback

Use a fake LLM returning an off-node tutor proposal.

Pass condition: proposal is rejected and deterministic fallback is recorded as `fallback_used`.

#### Gate to Enter the Next Phase

Required commands:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_tutor_agents.py tests/test_pedagogical_flow.py tests/test_llm.py -q
python -m compileall -q pelican_mvp
```

Success condition: fast/slow tutor proposals are distinct, validated, and safe. Do not proceed if slow-route behavior is only a label without separate executor logic.

#### Phase Commit

Commit message:

```bash
feat(pelican): split fast and slow tutor agents
```

Staging scope:

```bash
git status --short
git add misc/PELICAN_mvp/pelican_mvp/agents/fast_tutor_agent.py \
        misc/PELICAN_mvp/pelican_mvp/agents/slow_simulator_agent.py \
        misc/PELICAN_mvp/pelican_mvp/engine.py \
        misc/PELICAN_mvp/pelican_mvp/llm.py \
        misc/PELICAN_mvp/pelican_mvp/tutoring.py \
        misc/PELICAN_mvp/tests/test_tutor_agents.py \
        misc/PELICAN_mvp/tests/test_pedagogical_flow.py \
        misc/PELICAN_mvp/tests/test_llm.py
git diff --cached --check
git diff --cached --stat
git commit -m "feat(pelican): split fast and slow tutor agents"
git show --stat --oneline --summary HEAD
```

### Phase 5: Expose Agent Executor Trace in UI, Export, and Manual Experiment

#### Problem

After backend agents become real executors, the frontend/export must clearly show which agent produced which proposal and which proposal the pipeline adopted. Otherwise manual reviewers may still interpret the system as template-driven. The target state is an evidence-backed trace matching the methodology figure.

#### Assumptions

- Existing UI panels can be extended without a full redesign.
- Export may include learner-visible transcript but not raw hidden agent inputs or provider responses.
- Manual tests should reject agent labels that do not include accepted/rejected/fallback proposal evidence.

#### Solution

Extend API metadata, frontend panels, Markdown export, README, and manual test scripts to show:

```text
agent input ref → proposal artifact → validation status → adopted output ref → final learner-visible effect
```

#### Implementation

> Context: UI/export helpers must document why they expose only safe summaries. Python public helpers need Google-style docstrings. JavaScript comments should be added only around non-obvious privacy or trace-rendering boundaries, not around ordinary DOM rendering.

Use the existing `skill_artifact_summary`, `agent_proposals`, `tutor_proposal_trace`, and `evidence_response_trace` fields as the base, then expand them for all agents.

#### Expected File Tree After Phase 5

This tree is cumulative from Phase 4.

```text
misc/PELICAN_mvp/
├── README.md                                      [modified]
├── pelican_mvp/
│   └── server.py                                  [modified]
├── static/
│   ├── app.js                                     [modified]
│   ├── index.html                                 [modified]
│   └── styles.css                                 [modified]
├── docs/
│   ├── 2026_07_23_02_experiment/
│   │   └── Agentic_PELICAN_Agent_Executor_Implementation_plan.md [modified]
│   └── 2026_07_23_experiment/
│       └── Agentic_PELICAN_frontend_io_manual_test_script.md      [modified]
└── tests/
    ├── test_server.py                             [modified]
    └── test_e2e.py                                [modified]
```

#### Work List

1. [ ] Modify `misc/PELICAN_mvp/pelican_mvp/server.py`.
   - [ ] Add proposed `agent_executor_trace` metadata covering all recent agent proposals.
   - [ ] Extend `_markdown_export()` with an `Agent Executor Trace` section.
2. [ ] Modify `misc/PELICAN_mvp/static/index.html`.
   - [ ] Add a visible `Agent Executor Trace` panel.
3. [ ] Modify `misc/PELICAN_mvp/static/app.js`.
   - [ ] Add proposed `renderAgentExecutorTrace()` that renders role, artifact type, validation status, source, safe summary, and adopted output ref.
4. [ ] Modify `misc/PELICAN_mvp/static/styles.css`.
   - [ ] Keep desktop and 390×844 mobile layout usable.
5. [ ] Modify `misc/PELICAN_mvp/docs/2026_07_23_experiment/Agentic_PELICAN_frontend_io_manual_test_script.md`.
   - [ ] Add acceptance criteria that each methodology stage must show an agent executor proposal.
6. [ ] Modify `misc/PELICAN_mvp/README.md`.
   - [ ] Explain current agent executor architecture and fallback semantics.
7. [ ] Modify `misc/PELICAN_mvp/tests/test_server.py`.
   - [ ] Assert `agent_executor_trace` exists and excludes raw learner text.
8. [ ] Modify `misc/PELICAN_mvp/tests/test_e2e.py`.
   - [ ] Assert frontend shows Skill Agent and Tutor Agent executor trace after the Spring-and-Autumn manual flow.
   - [ ] Assert the visible diagnostic and skill artifact contain humanities/history terms and do not contain deep-learning/STEM labels.

#### Test Plan

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_server.py tests/test_e2e.py -q
python -m compileall -q pelican_mvp
node --check static/app.js
```

#### Expected Output / Result

The frontend and export visibly match the methodology figure: each stage has an agent executor, bounded proposal, validation status, and adopted effect. Manual experiments can distinguish real agent execution from mere labels.

#### Testing Script

##### Act 01: Manual Spring-and-Autumn Agent Trace

Run the Spring-and-Autumn history onboarding and answer the first diagnostic with a historically relevant answer.

Pass condition: UI shows Intake Agent, Skill Agent, Diagnosis Agent, State Agent, Policy Agent, and Tutor Agent executor trace.

##### Act 02: Export Reconstructs Agent Loop

Click Markdown export after one `unknown` response.

Pass condition: export contains `Agent Executor Trace` and links evidence, state, strategy, tutor proposal, and final message preview.

##### Act 03: Mobile Trace Usability

Open 390×844 viewport and complete onboarding.

Pass condition: trace panels are visible and chat input/send/reset remain clickable.

#### Gate to Enter the Next Phase

Required commands:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest tests/test_server.py tests/test_e2e.py -q
python -m compileall -q pelican_mvp
node --check static/app.js
```

Success condition: UI/export trace shows every real agent executor safely. If mobile layout fails, fix layout before final regression.

#### Phase Commit

Commit message:

```bash
feat(pelican): expose agent executor trace
```

Staging scope:

```bash
git status --short
git add misc/PELICAN_mvp/README.md \
        misc/PELICAN_mvp/pelican_mvp/server.py \
        misc/PELICAN_mvp/static/app.js \
        misc/PELICAN_mvp/static/index.html \
        misc/PELICAN_mvp/static/styles.css \
        misc/PELICAN_mvp/docs/2026_07_23_02_experiment/Agentic_PELICAN_Agent_Executor_Implementation_plan.md \
        misc/PELICAN_mvp/docs/2026_07_23_experiment/Agentic_PELICAN_frontend_io_manual_test_script.md \
        misc/PELICAN_mvp/tests/test_server.py \
        misc/PELICAN_mvp/tests/test_e2e.py
git diff --cached --check
git diff --cached --stat
git commit -m "feat(pelican): expose agent executor trace"
git show --stat --oneline --summary HEAD
```

### Cross-Phase Regression and Final Acceptance

Final regression commands:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pytest -q
python -m compileall -q pelican_mvp
node --check static/app.js

cd /workspaces/AREQA
npm run check:report:strict
git status --short
git log --oneline -8
```

Manual rerun scenario:

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pelican_mvp --port 8000 --pelican-log debug --pelican-log-channels api,intake,skill,diagnosis,edf,memory,tutor,methodology
```

Open:

```text
http://127.0.0.1:8000/?learner_id=manual_agentic_pelican_20260723_agents
```

Run:

```text
Topic: 中國春秋時期歷史
Goal: 想理解春秋時期的政治秩序和諸侯爭霸脈絡
Level: 只有大概聽過春秋五霸，沒有系統學過
Answer 1: 因為周王室控制力下降，諸侯需要在名義上的周禮秩序下競爭主導權
Answer 2: 我不知道
Answer 3: 這太細了，我完全沒有基礎
```

Acceptance outcomes:

- Each methodology stage has a concrete agent executor proposal, not only a role label.
- Skill construction is owned by `SkillAgent` and records catalog/cache/runtime/generic/fallback status.
- The Spring-and-Autumn history scenario produces visible humanities/history skill artifacts and diagnostics, not deep-learning/STEM content.
- Full frontend manual acceptance for the Spring-and-Autumn script requires an accepted `runtime_generated` or `runtime_cache` humanities skill. A `generic:humanities` fallback run is acceptable only as an honest degradation/fallback verification, not as a full agentic executor pass.
- If the Spring-and-Autumn run falls back, the UI/export must explicitly show fallback status and must not claim accepted runtime generation.
- Diagnosis, State, Policy, Fast Tutor, and Slow Simulator agents each emit bounded proposals.
- `PelicanEngine` remains final mutation owner and rejects invalid proposals fail-closed.
- UI/export can reconstruct agent input ref → proposal artifact → validation → adopted output.
- Logs include safe event names, correlation IDs, role/stage/source/status/reason codes, and no raw learner answer, prompts, model output, provider body, credentials, or hidden reasoning.
- Final `git status --short` shows no planned tracked changes. Existing unrelated experiment artifacts may remain untracked only if they pre-existed and are intentionally excluded.

Remaining risks and mitigations:

- Runtime-generated skills may be structurally valid but pedagogically weak. Mitigation: add pedagogical quality scoring and golden skill fixtures after SkillAgent extraction.
- Domain routing is still alias-heavy. Mitigation: add a semantic router agent or expand aliases/golden cases in a later phase.
- Full agent extraction may increase indirection. Mitigation: keep each phase small, preserve deterministic fallback, and require phase commits with passing gates.
- LLM availability remains deployment-dependent. Mitigation: every agent must expose explicit fallback status and must not represent fallback as accepted runtime generation.
