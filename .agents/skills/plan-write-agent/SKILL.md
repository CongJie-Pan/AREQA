---
name: plan-write-agent
description: Write reviewable, phase-based software implementation plans in English. Use when planning a feature, refactor, bug fix, architecture change, or cross-system change before implementation. Every phase defines the problem, assumptions, solution, implementation, expected file tree, checkbox work list, test plan, expected result, concise Act-based testing script, and a mandatory test gate.
---

# Plan Write Agent

Produce an implementation plan that another engineer can execute and verify without reconstructing the design decisions. Write in clear, natural, professional English unless the user explicitly requests another language. Use paragraphs for reasoning; use tables, lists, and trees only where they make execution or review clearer.

## Workflow

1. Read the user request, relevant documentation, source entry points, callers, tests, configuration, and repository structure before drafting the plan.
2. Identify the current behavior, target behavior, data flow, compatibility boundaries, dependencies, and regression risks. Treat unknown facts as assumptions, validation tasks, or risks; never present them as confirmed.
3. Divide the work into dependency-ordered phases. Each phase must be independently implementable and verifiable. Resolve data ownership, invariants, failure handling, and terminal observability before larger structural refactors.
4. Do not modify production code when the user asks only for a plan. Write the plan into the requested document and preserve unrelated user changes.

## Required Phase Format

Start with one short paragraph summarizing the objective, current understanding, and why the phase order is appropriate. Then use the following structure for every phase. Do not omit or rename the required sections.

```markdown
### Phase N: Clear Phase Name

#### Problem

Explain the current failure or limitation, trigger, affected behavior, and observable target state.

#### Assumptions

State confirmed constraints, compatibility boundaries, unresolved decisions, and the consequence if an assumption is false.

#### Solution

Explain the selected design, ownership boundaries, data/control flow, and material tradeoffs.

#### Implementation

> Context: State the required code-commenting approach for this phase. Require Google-style docstrings for every new or materially changed public module, class, and function. Explain the non-obvious design rationale, invariants, ownership boundaries, compatibility constraints, failure semantics, and critical structured-log emissions that must be documented. Require inline comments at complex decisions or state transitions only when they explain *why* the code is written that way; never use comments to repeat obvious syntax, assignments, or control flow. Require enough meaningful documentation for a future maintainer to safely change the phase's highest-risk paths.

Specify the intended files, symbols, interfaces, data/schema changes, error handling, migration/compatibility behavior, configuration, and implementation order. Clearly label files that will be added.

#### Expected File Tree After Phase N

Show only files expected to be added, modified, or removed by this phase. Mark entries as `[new]`, `[modified]`, or `[removed]`. State explicitly when the tree is cumulative.

```text
backend/
├── existing_module.py                  [modified]
└── services/
    └── new_service.py                  [new]
tests/
└── test_new_service.py                 [new]
```

#### Work List

Write an implementation checklist immediately after the file tree. Every top-level item must name the exact repository path and the affected existing function/class, or label a proposed new symbol explicitly; nested sub-work must name the symbol or code path it changes. State the intended code change, not merely an outcome such as "refactor memory" or "add tests." Make test tasks name the target test files and the behavior they protect. Use numbered top-level work items and nested checkbox sub-work only when a subtask is necessary. Keep items concrete, ordered, and traceable to the implementation and file tree. Use this format:

```markdown
1. [ ] Create `backend/services/new_service.py`.
   - [ ] Add the proposed `NewInput` type and `handle_new_input()` method.
   - [ ] Update `ExistingService.execute()` in `backend/services/existing_service.py` to call it.
2. [ ] Modify `backend/legacy_module.py`.
   - [ ] Remove `LegacyDecision` only after migrating its callers.
3. [ ] Extend `tests/backend/test_new_service.py` with the regression case for rejected input.
```

#### Test Plan

Describe unit and integration coverage, including success, failure, and boundary cases. Name test files, fixtures/mocks, required assertions, and executable commands.

#### Expected Output / Result

State the observable behavior, persisted state, logs/events, API/SSE behavior, or UI outcome that proves the phase worked. Keep this distinct from the implementation steps and test commands.

#### Testing Script

Write a concise, sequential test scenario using Acts. Each Act must test one behavior, contain a precise input/action or setup, and finish with one clear pass condition. Use this format:

##### Act 01: Short Behavior Title

Describe the exact input, setup, or action.

Pass condition: state the single observable result.

Use as many Acts as necessary, but keep every Act narrow. Prefer realistic user input for user-facing behavior and deterministic setup for background jobs, recovery, or failure paths. Do not replace this script with a broad checklist or merely repeat automated test names.

#### Gate to Enter the Next Phase

List the exact commands and required checks. Define the success condition, evidence to retain, and required response to failure. The next phase must not start until every gate passes; do not weaken assertions, skip failing tests, or mark failures flaky to proceed.
```

## Plan Quality Requirements

- Keep phase scope coherent. Do not split work only to create more phases.
- Prefer existing project patterns, names, and tests. Do not invent files or APIs without marking them as proposed additions.
- Make all external contracts explicit: API responses, SSE events, database records, queues, logs, configuration, and frontend behavior when relevant.
- Define terminal observability for every changed critical path. Require structured logs through the project's existing logging abstraction, with stable event names, appropriate correlation IDs, state/result, and safe reason codes. Specify log levels for success, policy block/retry, and unexpected failure. Never require `print` statements or human-only free-form logs.
- Treat logs as a privacy boundary. Exclude raw user text, prompts, model output, credentials, tokens, sensitive labels, and other unnecessary personal data. Require tests to capture critical events and assert event names plus safe metadata rather than formatted log sentences.
- For migrations, describe treatment of legacy records, incomplete provenance, retries, idempotency, rollback, and fail-closed behavior where applicable.
- Make test coverage proportional to risk. Shared data paths, background jobs, public streaming contracts, and user profile writes require focused regression and integration tests.
- Begin every Implementation section with a phase-specific `> Context:` block defining the required Google-style docstrings, rationale-focused inline comments, and critical structured-log documentation. Put expected file trees, detailed file/function-level checkbox work lists, expected results, and Act-based scripts in every phase. For critical state transitions, include safe structured-log work and test assertions. These are mandatory review artifacts, not optional additions.

## Cross-Phase Regression and Final Acceptance

End every plan with `### Cross-Phase Regression and Final Acceptance`. Include the full regression command, focused commands omitted from the full suite, the end-to-end or manual rerun scenario, concrete acceptance outcomes, remaining risks, and mitigations. State any unresolved product or deployment decisions explicitly.

## Final Review

Before delivering, confirm that every phase has all ten required sections: Problem, Assumptions, Solution, Implementation, Expected File Tree, Work List, Test Plan, Expected Output / Result, Testing Script, and Gate. Confirm that each Implementation heading is immediately followed by a phase-specific `> Context:` block; the output is English; every work-list item names a file and symbol or explicitly proposed new symbol; test work names test files; file paths and commands are concrete; Act scripts are concise; and no phase can proceed without passing its stated verification gate.
