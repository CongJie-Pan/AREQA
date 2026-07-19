# PELICAN MVP Learning Engine Experiment Protocol

## 1. Overview
This document specifies the manual experiment testing protocol for the `misc/PELICAN_mvp` AI learning engine. This phase verifies the behavior of the newly integrated dynamic learning components: dynamic plan generation, successor-first diagnosis, Epistemic Development Framework (EDF) policy alignment, and independent learning memory persistence. 

This experiment acts as the final promotion gate before adopting the MVP architecture into the production AREQA backend.

## 2. Environment Setup
1. Use an isolated or cleanly cloned workspace.
2. Ensure the temporary state `misc/PELICAN_mvp/data/demo_student.json` is cleared or reset before starting.
3. Start the test server:
   ```bash
   cd misc/PELICAN_mvp
   python -m pelican_mvp.server
   ```
4. Access the web dashboard at `http://127.0.0.1:8123`.

## 3. Manual Experiment Acts & Expected Behavior

### Act 01: Initial Intake (Onboarding)
- **Action**: Open the dashboard without any query parameters.
- **Capture Field**: UI state (`#phase-display`, `tree-node` region).
- **Success Criteria**:
  - The UI correctly labels the phase as `onboarding`.
  - The legacy curriculum selector is not present.
  - The assistant asks an open-ended intake question (e.g., "What do you want to learn?").
- **Failure Criteria**: System attempts to load a hardcoded curriculum tree immediately.

### Act 02: Dynamic Planning & Validation
- **Action**: In Rule (Deterministic) Mode, input the learning goal: `I want to understand why binary search needs sorted data; I get confused about the boundaries.`
- **Capture Field**: Plan Source, Topic, and Knowledge State Tree.
- **Success Criteria**:
  - Phase advances from `onboarding` to `diagnosis`.
  - The Knowledge State Tree is populated with Fallback/Generated nodes.
  - The EDF State switches to `EXPLORING` (or similar initial state).
  - Memory Summary correctly shows `1` context interaction.

### Act 03: Successor-First Diagnosis
- **Action**: Provide the expected string (e.g., `進階答案`) to trigger an evaluation.
- **Capture Field**: Diagnostic prompts, EDF Policy updates.
- **Success Criteria**:
  - The engine correctly questions the learner from the successor (leaf) nodes backwards to the foundation nodes.
  - Correct/incorrect answers trigger state updates that flip node visualization from grey (`undiagnosed`) to green (`mastered`) or red (`not_mastered`).
  - The EDF policy adapts dynamically without showing raw engine prompts to the learner.

### Act 04: Reset & Fixture Compatibility
- **Action**: 
  - Click the **Reset** button on the UI.
  - Make a direct API POST to `/api/start` with `{"learner_id": "test", "curriculum_id": "cnn"}`.
- **Capture Field**: Browser session state, API response JSON.
- **Success Criteria**:
  - Clicking Reset properly discards the current plan and restores `onboarding` mode.
  - Calling the API directly with a fixed curriculum ID bypasses `onboarding` and successfully initializes the static tree (historical regression preservation).

### Act 05: LLM Generation Robustness
- **Action**: Supply valid OpenRouter credentials via `OPENROUTER_API_KEY`. Switch to `LLM-based` mode and enter a complex topic like `React useEffect dependency arrays`.
- **Capture Field**: Generated tree JSON schema in network panel.
- **Success Criteria**:
  - The LLM safely returns a JSON structure mapping to `LearningPlanSnapshot`.
  - Invalid schema falls back gracefully to deterministic rule-mode without crashing the UI.

## 4. Promotion Decision Checklist

- [ ] All 5 Acts complete successfully.
- [ ] No internal Python `Traceback` is leaked to the UI or API response.
- [ ] XSS safety verified (no unescaped HTML injection via topic names).
- [ ] `demo_student.json` structure matches versioned schema constraints (`schema_version >= 2`).
- [ ] The core `backend/` engine remains completely unpolluted by MVP experimental logic.

If the above checklist is satisfied, the Dynamic AI Learning Engine architecture is considered **APPROVED** for promotion phase planning.
