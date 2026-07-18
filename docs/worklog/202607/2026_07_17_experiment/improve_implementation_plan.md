# 2026-07-17 Experiment Improvement Implementation Plan

This plan addresses the direct failures, evidence gaps, and protocol deviation documented in the revised 17 July experiment report. The phases are ordered by dependency and risk: repair the confirmed profile-edit failure; prevent unsupported learner-state claims at the response boundary; make memory lifecycle assertions observable; make web citations verifiable; and finally make ComPeer execution diagnosable and reproducible. Acts 03 through 10 were not established as passes by the original artifacts, so this plan treats them as validation work rather than assumed product failures. Each phase is independently testable and committed only after its gate passes.

## Implementation Status (2026-07-18)

All five implementation phases and their automated gates are complete. Checked work-list items below mean the implementation or automated verification exists and passed; they do not claim that a new manual run of `test_script_new.md` has been performed. The historical experiment remains failed/not verified as documented in `experiment_report.md`, while the new manual script is the acceptance procedure for a future clean-account run.

Automated final gate: backend `385 passed, 3 skipped`; frontend `127 passed`; strict ESLint and TypeScript checks passed; Next.js production build passed. Phase commits are `41c0171`, `acaf7a1` / `3605365` / `a206739`, `893fc77` / `8d8aad6`, `326bcb6`, and `08895af` / `a9258e9`.

### Audit Follow-up Status (2026-07-18)

An implementation audit of `41c0171^..cc77ca4` found that several checked items were only partially implemented or were verified from pre-existing code rather than completed in that audited range. The follow-up commits below close those audit gaps and supersede the earlier over-broad status interpretation:

- `3c75855 fix(search): fail closed on malformed citation sources` completed web-source URL validation, malformed-source backend coverage, and structured citation panel tests.
- `5154ff0 fix(safety): broaden learner-state response guard` expanded deterministic response-boundary coverage for unsupported emotional-state, ability, mastery, understanding, and progress claims while preserving user-attributed acknowledgements.
- `438bbda test(memory-mailbox): close observability audit gaps` added temporary-goal lifecycle metadata, prompt-focus clearing logs, and mailbox/reconciliation safety assertions.

Focused follow-up gates passed: `tests/backend/test_perplexity_node.py` (`4 passed`); frontend citation/export tests (`6 passed`); response-boundary/context/stream endpoint tests (`21 passed, 1 skipped`); memory/mailbox focused tests (`41 passed`); `git diff --check` passed for each follow-up phase. These automated gates still do not claim that the manual `test_script_new.md` journey has been rerun.

### Phase 1: Restore Explicit Profile-Memory Editing

#### Problem

Act 08A failed because `PUT /api/v1/memory/profile:explicit:<id>` returned HTTP 500. `edit_memory_endpoint()` uses the module-level `json` name before later local `import json` statements in the same function. Python therefore resolves `json` as an uninitialized local variable on the explicit-profile branch. The existing endpoint test covers only the generic GUM-memory branch, so it did not protect this public API contract.

#### Assumptions

The Redis user profile remains the durable source of truth for `explicit_memories`, while working memory is a best-effort prompt cache. The current memory ID derivation remains compatible. If a requested explicit-memory ID does not exist, the endpoint should fail explicitly rather than return a false success; this behavior must be confirmed against the existing delete semantics during implementation.

#### Solution

Use the module-level `json` import consistently and extract the explicit-profile update into a small internal helper that owns validation, durable persistence, working-memory synchronization, and safe correction logging. The durable profile update must succeed before the endpoint returns success. A working-memory synchronization failure must be observable but must not turn an already-persisted edit into a 500 response.

#### Implementation

> Context: Add Google-style docstrings to the new or materially changed explicit-profile helper and endpoint. Document why the profile record is the durable source of truth, why the working-memory mirror is non-critical, and why correction logs exclude edited text. Add inline comments only at the durable-write and cache-sync boundary to explain failure semantics; do not narrate ordinary assignments or branches.

Modify `backend/main.py` to remove function-local `json` imports from `edit_memory_endpoint()` and reuse the module import. Add a proposed internal helper, for example `_update_explicit_profile_memory()`, which returns a typed success/not-found result after a profile write. It must emit `memory.correction_applied` at `INFO` with safe metadata (`user_id`, memory ID, operation, result) and emit `memory.correction_sync_failed` at `WARNING` when the non-critical working-memory mirror cannot be updated. Do not log the edited text.

Extend the endpoint tests to patch the global memory store, update an explicit profile record, fetch the stored profile after the request, and verify that the endpoint handles an unavailable or failing working-memory mirror without losing the durable edit. Update the manual script so edit and delete are separate dependent Acts: Act 08A may pass only on HTTP 2xx plus reload confirmation; Act 08B starts only after Act 08A passes.

#### Expected File Tree After Phase 1

This tree is cumulative only within this plan.

```text
backend/
└── main.py                                                   [modified]
tests/backend/
└── test_gum_endpoints.py                                     [modified]
docs/worklog/202607/2026_07_17_experiment/
└── test_script_new.md                                         [new]
```

#### Work List

1. [x] Modify `backend/main.py`.
   - [x] Add the proposed `_update_explicit_profile_memory()` helper adjacent to `_delete_explicit_profile_memory()`.
   - [x] Update `edit_memory_endpoint()` to call the helper for `profile:explicit:` IDs and remove its local `import json` statements.
   - [x] Preserve a durable profile update when `MemoryStore.update_working_memory()` raises, while emitting `memory.correction_sync_failed` with safe metadata only.
   - [x] Emit `memory.correction_applied` only after the profile write succeeds; return a non-success response for an unknown explicit memory ID.
2. [x] Extend `tests/backend/test_gum_endpoints.py`.
   - [x] Add a regression for `PUT /api/v1/memory/profile:explicit:<id>` that asserts HTTP 2xx, changed `explicit_memories`, and a successful reload from the mocked store.
   - [x] Add a test that a working-memory synchronization exception is logged safely and does not undo the persisted profile edit.
   - [x] Add a not-found test for an explicit memory ID that does not belong to the authenticated profile.
3. [x] Create `docs/worklog/202607/2026_07_17_experiment/test_script_new.md` from the historical script.
   - [x] Keep it focused on manual user-journey behavior and split Act 08 into edit/reload and delete/reload steps.
   - [x] Require recording endpoint, HTTP status, memory ID, safe error code, and refresh result; prohibit Act 08B after an Act 08A failure.
   - [x] Keep routine evidence lightweight; require the test account, time, visible result, and screenshot only when an Act fails, plus `T0` for the mailbox Act.

#### Test Plan

Use `tests/backend/test_gum_endpoints.py` to protect the exact explicit-profile route, rather than only the legacy numeric route. Mock Redis and the memory store to assert profile persistence, cache-sync isolation, not-found behavior, and safe structured events. Run the endpoint suite plus the focused memory-view regression tests because the edit result must survive a subsequent memory fetch.

```bash
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_gum_endpoints.py \
  tests/backend/test_memory_injection_regression.py
```

#### Expected Output / Result

An explicit profile-memory edit returns HTTP 2xx, persists the replacement value in the profile store, and remains visible after a reload. A cache-sync failure results in a safe warning rather than a 500 or lost durable change. The terminal records `memory.correction_applied` without raw edited text.

#### Testing Script

##### Act 01: Edit an Explicit Profile Memory

Create or select one verified explicit profile memory. Change it to a distinct low-risk preference value and record the request endpoint, memory ID, and HTTP status.

Pass condition: the edit request returns HTTP 2xx and the refreshed memory page shows the new value.

##### Act 02: Delete Only After a Successful Edit

Run this Act only when Act 01 passed. Delete the edited memory and refresh the page.

Pass condition: the deleted memory is absent after refresh and no stale value reappears.

#### Gate to Enter the Next Phase

Run the focused command above and retain its output. Run `git diff --check`. Execute Act 01 and, only after it passes, Act 02 against a clean test account. Retain HTTP status, memory ID, reload result, and safe correction event names. Do not enter Phase 2 if any explicit-profile edit returns a 4xx/5xx response, if the changed value fails to persist, or if a test exposes edited text in logs.

#### Phase Commit

Create one phase commit after the gate passes:

```text
fix(memory): restore explicit profile memory editing
```

Inspect `git status --short` and preserve unrelated changes. Stage only `backend/main.py`, `tests/backend/test_gum_endpoints.py`, and `docs/worklog/202607/2026_07_17_experiment/test_script_new.md`. Run `git diff --cached --check` and `git diff --cached --stat`, then commit. Confirm with `git show --stat --oneline --summary HEAD` before Phase 2. Do not amend, rewrite, or push existing commits.

### Phase 2: Enforce Response-Boundary Safety

#### Problem

Acts 01 and 02 have direct response-boundary failures. The assistant described the user's science foundation as weak and later asserted that the user had understood inertia. The script forbids capability, anxiety, and understanding claims without independent verified evidence. `ConversationContextService` already appends an understanding rule to the prompt, but prompt-only instruction did not prevent the observed output.

#### Assumptions

The system may acknowledge a user's request and teach at an appropriate level, but it must not transform a user disclosure into an assistant-authored fact about ability, emotion, mastery, or learning progress. Verified profile evidence, if any, remains governed by the existing memory policy; a model inference, hot-memory learner state, or a single user message is not sufficient verification. A deterministic response guard must preserve legitimate educational explanations and source citations.

#### Solution

Strengthen the prompt contract and add a narrow response-boundary validator at the final-answer boundary. The validator will reject or repair only unsupported assertions about learner ability, emotional state, or understanding; it will not decide memory eligibility or alter durable state. The structured source contract remains the authority for factual citations and is handled in Phase 4.

#### Implementation

> Context: Add Google-style docstrings to every new or materially changed public validator and context-building method. Document why prompt guidance is insufficient on its own, which claims require verified evidence, how the validator fails safely, and why it does not inspect or persist personal data. Add inline comments only at the point where a generated response is checked or repaired and where a safe violation event is emitted; do not comment ordinary string processing.

Modify `backend/services/conversation_context_service.py` to make the response-boundary instruction explicit: user disclosures may be acknowledged without being restated as a diagnosis or ability judgment, and the assistant must not claim understanding, mastery, ability, anxiety, or progress without independently verified evidence. Add a `ResponseBoundaryValidator` and streaming boundary filter in `backend/services/response_boundary_validator.py`, then invoke them from `backend/services/conversation_stream_service.py` after generation and before SSE content is emitted. The validator returns a safe replacement without writing memory. Emit `orchestration.response_boundary_blocked` at `WARNING` with run ID, category, and safe reason code only; do not log response text or user text.

Add focused tests with deterministic model output that reproduces the two observed failures and control cases that contain neutral educational language. Update `test_script_new.md` so Acts 01 and 02 require a visible-response review; durable-store verification remains an engineering or automated-test responsibility, not a manual-tester task.

#### Expected File Tree After Phase 2

This tree is cumulative with Phase 1.

```text
backend/services/
├── conversation_context_service.py                            [modified]
├── conversation_stream_service.py                            [modified]
└── response_boundary_validator.py                             [new]
tests/backend/
├── test_conversation_context_service.py                       [new]
└── test_response_boundary_validator.py                        [new]
docs/worklog/202607/2026_07_17_experiment/
└── test_script_new.md                                          [modified]
```

#### Work List

1. [x] Create `backend/services/response_boundary_validator.py`.
   - [x] Add the proposed `ResponseBoundaryValidator.validate()` interface and typed result for permitted, retry, and safe-replacement outcomes.
   - [x] Define allowlisted violation categories for unsupported ability, emotional-state, understanding, mastery, and progress assertions; exclude user text and model text from events.
2. [x] Modify `backend/services/conversation_context_service.py`.
   - [x] Update `ConversationContextService.build_conversation_context()` with explicit rules against converting user disclosures into assistant judgments and against unsupported understanding claims.
3. [x] Modify `backend/services/conversation_stream_service.py`.
   - [x] Apply the streaming response-boundary filter before SSE content emission and final persistence.
   - [x] Emit `orchestration.response_boundary_blocked` with run ID and reason code when the validator prevents an unsafe final answer.
4. [x] Create `tests/backend/test_response_boundary_validator.py` and `tests/backend/test_conversation_context_service.py`.
   - [x] Add regressions for the Act 01 weak-foundation assertion and the Act 02 understood-inertia assertion.
   - [x] Add controls proving a neutral explanation and a user-attributed acknowledgement remain permitted.
5. [x] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_new.md`.
   - [x] Require separate visible-response and durable-state evidence for Acts 01 and 02.
   - [x] Define any unsupported assistant claim as an immediate Act failure even when no durable write occurred.

#### Test Plan

Use deterministic generated-answer fixtures so the tests do not depend on a live model. Assert that the validator catches the two observed claims, permits neutral teaching, and emits only allowlisted metadata. Run context-service coverage to ensure the final system prompt contains the strengthened boundary instruction.

```bash
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_response_boundary_validator.py \
  tests/backend/test_conversation_context_service.py \
  tests/backend/test_conversation_stream_service.py
```

#### Expected Output / Result

The assistant can teach from the user's requested level without declaring that the user is weak, anxious, understands, or has mastered a concept unless independently verified evidence authorizes that claim. Unsafe final text is never persisted as a completed assistant answer, and the system records a safe, correlated violation event.

#### Testing Script

##### Act 01: Reject an Unsupported Ability Claim

Use deterministic generated text that says the user has a weak science foundation after the Act 01 input.

Pass condition: the text is blocked or safely replaced, and no durable memory write occurs.

##### Act 02: Reject an Unsupported Understanding Claim

Use deterministic generated text that says the user already understands inertia after the Act 02 input.

Pass condition: the text is blocked or safely replaced, and the visible final response makes no mastery claim.

#### Gate to Enter the Next Phase

Run the focused command above, `git diff --check`, and Acts 01 and 02 against a clean account. Retain the final visible response, response-boundary event name/reason code, and cold/profile postcondition snapshot. Do not enter Phase 3 if either prohibited claim reaches the user, if the guard persists raw text in logs, or if a legitimate neutral explanation is blocked.

#### Phase Commit

Create one phase commit after the gate passes:

```text
fix(safety): prevent unsupported learner-state claims
```

Inspect `git status --short` and preserve unrelated changes. Stage only the Phase 2 service files, Phase 2 tests, and relevant `test_script_new.md` hunks. Run `git diff --cached --check` and `git diff --cached --stat`, commit, and confirm with `git show --stat --oneline --summary HEAD` before Phase 3. Do not amend, rewrite, or push existing commits.

### Phase 3: Make Memory-Governance Evidence Verifiable

#### Problem

Acts 03 through 07 produced useful decision logs, but the run did not prove all required durable states. It did not record candidate status, exact expiration, final evidence counts, unique conversation/message counts, source role/provenance, or profile counts. Consequently, the experiment cannot distinguish safe deduplication from an unintended new candidate, prove that Act 03 made no candidate/profile write, prove temporary-goal removal prevents future personalization, or prove that GUM-derived anxiety, ability, interest, and one-off search context remained out of cold/profile storage.

#### Assumptions

`MemoryStore` remains the authoritative owner of cold candidates, verified profile memory, and promotion invariants. The product memory page must continue to hide candidates and operational state from ordinary users. Manual validation can use authenticated engineering access to the same test account's backing store; no public API that exposes candidate evidence or sensitive data will be added.

#### Solution

Strengthen safe lifecycle observability at the storage boundary and make a read-only, test-account-only state snapshot available to engineering validation and automated tests. Storage events will carry counts, IDs, categories, status, and reason codes, but never raw evidence or model output. `test_script_new.md` remains a visible user-journey script and refers failures to engineering rather than requiring a tester to inspect snapshots.

#### Implementation

> Context: Add Google-style docstrings to materially changed memory-store and ingestion methods. Document why candidate evidence remains internal, why log metadata is count-and-ID based, why one conversation cannot corroborate a passive preference twice, and why incomplete or model-derived data fails closed. Add inline comments only at duplicate-evidence and promotion-state transitions to explain the invariant being preserved.

Modify `backend/memory_store.py` so `append_cold_candidate()` emits a safe event after its transaction commits. The event must distinguish `evidence_appended`, `duplicate_message_ignored`, and `duplicate_conversation_ignored`, including candidate ID, category, candidate status, evidence count, distinct conversation count, and correlation IDs. Update `promote_cold_candidate()` and temporary-goal completion paths to include lifecycle status and independent-evidence counts in their existing safe events. Do not alter the existing eligibility or promotion thresholds merely to satisfy logging.

Modify `backend/services/memory_ingestion_service.py` to pass the safe correlation fields through its terminal decision events and to report a candidate snapshot reference after canonical matching or promotion. Extend regression tests around store state, not only log strings. Document the pre-Act snapshot, post-Act snapshot, and cleanup record for engineering validation; keep `test_script_new.md` limited to visible behavior and failure artifacts.

#### Expected File Tree After Phase 3

This tree is cumulative with Phases 1 and 2.

```text
backend/
├── memory_store.py                                           [modified]
└── services/
    └── memory_ingestion_service.py                           [modified]
tests/backend/
├── test_memory_store.py                                      [modified]
├── test_memory_ingestion_service.py                          [modified]
└── test_memory_injection_regression.py                       [modified]
docs/worklog/202607/2026_07_17_experiment/
└── test_script_new.md                                         [modified]
```

#### Work List

1. [x] Modify `backend/memory_store.py`.
   - [x] Update `MemoryStore.append_cold_candidate()` to emit one safe post-transaction evidence event with candidate ID, category, status, evidence count, distinct conversation count, and duplicate reason when applicable.
   - [x] Update `MemoryStore.promote_cold_candidate()` to include independent-evidence counts and lifecycle status in `memory.profile_promoted` and `memory.promotion_blocked` events.
   - [x] Update the temporary-goal completion path to emit completed status and the safe working-memory keys cleared, without message content.
2. [x] Modify `backend/services/memory_ingestion_service.py`.
   - [x] Update `MemoryIngestionService.ingest_user_evidence()` terminal logs to carry message ID, conversation ID, candidate ID when available, category, state, and reason code only.
   - [x] Preserve the rule that semantic analysis is advisory and cannot authorize a profile write or append evidence for rejected input.
3. [x] Extend `tests/backend/test_memory_store.py`.
   - [x] Add assertions that a same-conversation repeat and a duplicate message ID leave candidate evidence and distinct-conversation counts unchanged.
   - [x] Add assertions that expired, completed, cross-user, and wrong-category candidates cannot be promoted or merged.
4. [x] Extend `tests/backend/test_memory_ingestion_service.py` and `tests/backend/test_memory_injection_regression.py`.
   - [x] Assert that Act 03 interrogative preference questions, sensitive content, one-off SpaceX context, and GUM/model inference do not create cold or profile records.
   - [x] Assert that the equivalent-preference pair creates one canonical candidate and exactly one profile entry after two distinct conversations.
   - [x] Assert that a completed temporary goal is absent from prompt-safe personalization and cannot be promoted, and that an explicit command profile write records user source role, original message ID, low-risk classification, and non-sensitive result.
   - [x] Capture structured logs and assert that they include safe counts and identifiers but not raw user text, evidence quotes, sensitive labels, or model output.
5. [x] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_new.md`.
   - [x] Keep only user-visible pass/fail conditions and the minimum screenshots/timestamps needed to reproduce a failure.
   - [x] Refer candidate counts, provenance, cleanup, and forbidden-record checks to the Phase 3 automated/engineering validation procedures rather than asking manual testers to collect them.

#### Test Plan

Run focused store and ingestion tests with controlled Redis fixtures. Cover first candidate creation, canonical append, same-conversation repeat, duplicate message replay, concurrent promotion, expiration, completion, cross-user isolation, category mismatch, sensitive rejection, and model-inference rejection. Capture log records through `caplog` and assert only event names and allowlisted metadata.

```bash
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_memory_store.py \
  tests/backend/test_memory_ingestion_service.py \
  tests/backend/test_memory_injection_regression.py \
  tests/backend/test_memory_source_boundaries.py \
  tests/backend/test_real_memory_pipeline.py
```

#### Expected Output / Result

Every memory Act can show its durable before/after state without exposing internal candidates to normal product users. A reviewer can prove that the canonical preference has one candidate and one promoted profile entry, that repeated same-conversation evidence did not corroborate it, and that forbidden inferred or sensitive records never reached cold/profile state.

#### Testing Script

##### Act 01: Record a Clean Memory Baseline

Create a new test account and record candidate count, verified-profile count, hot-memory keys, pending mailbox tasks, and cooldown state before sending any message.

Pass condition: all state is empty or explicitly identified as pre-existing and excluded from the run.

##### Act 02: Verify a Rejected Sensitive Learning Question

Send the Act 01 learning question, wait for post-turn work, then inspect cold candidates and verified profile for the test account.

Pass condition: no sensitive, ability, anxiety, or inferred learner-state record exists in cold or verified profile memory.

##### Act 03: Verify Query and Lifecycle Postconditions

Send the Act 03 preference question, complete the Act 06 temporary-goal sequence, and issue the Act 07 explicit-memory command on isolated test accounts. Inspect the documented state snapshot after each action.

Pass condition: Act 03 has no candidate or profile record; Act 06 is completed and unavailable to personalization/promotion; Act 07 has one persisted low-risk profile record with user-source provenance.

##### Act 04: Verify Independent Preference Corroboration

Send the two equivalent preference declarations in distinct conversations, then replay one declaration in the second conversation and replay its message ID.

Pass condition: one candidate and one profile memory exist with exactly two distinct conversation IDs and two distinct message IDs; both replays leave counts unchanged.

#### Gate to Enter the Next Phase

Run the focused command above and retain output plus a redacted test-account state snapshot. Run `git diff --check`. Execute the four Acts against clean accounts and retain safe event names, candidate/profile counts, category/status, expiry/completion state, provenance fields, and distinct-ID counts. Do not proceed if a forbidden durable record exists, a replay changes corroboration counts, a required field is missing, a temporary goal remains personalization-eligible after completion, explicit-command provenance is incomplete, or logs reveal raw evidence.

#### Phase Commit

Create one phase commit after the gate passes:

```text
test(memory): make governance lifecycle evidence auditable
```

Inspect `git status --short` first. Stage only `backend/memory_store.py`, `backend/services/memory_ingestion_service.py`, the named memory test files, and the Phase 3 test-script hunks. Run `git diff --cached --check` and `git diff --cached --stat`, commit, and verify with `git show --stat --oneline --summary HEAD`. Do not stage unrelated experiment artifacts or prior report files.

### Phase 4: Make Search Citations Verifiable in the User Interface

#### Problem

Act 02 showed inline numeric citation markers, but the saved transcript did not contain a source name, URL, or observable mapping from marker to source. The backend emits structured `sources` events and the frontend has citation code, but the current evidence does not identify whether loss occurs during streaming, persistence, rendering, or transcript capture. The plan must diagnose that boundary before claiming a specific implementation defect.

#### Assumptions

The source payload may contain untrusted external URLs and titles. The frontend must continue to use safe external-link attributes and must not manufacture citations when search produced no source payload. Citation markers in model text are not independently trustworthy; they are only navigational affordances when a same-message structured source collection exists.

#### Solution

Treat structured source payload as the authority. Preserve it from the SSE `sources` event to the persisted assistant message, render a visible source list with title/domain and URL affordance for every sourced answer, and disable inline marker interaction when the corresponding indexed source is absent. Keep the backend payload contract stable and add end-to-end tests that fail if a response retains markers but loses sources.

#### Implementation

> Context: Add Google-style docstrings or TSDoc to materially changed source-payload handling functions and components. Document why structured sources, rather than model-authored marker text, are authoritative; why an absent mapping must fail closed in the UI; and why external URLs require existing safe-link handling. Use inline comments only where stream completion attaches sources to the persisted message or where indexed marker lookup rejects an invalid mapping.

Modify `frontend/src/services/chat/index.ts` so each streaming execution path attaches the structured `sources` payload to the same assistant message before persistence and clears per-request source state when a stream is cancelled or fails. Modify `frontend/src/components/MessageList/MessageItem.tsx` and `frontend/src/components/Citations/index.tsx` so a message with structured sources shows a visible, expandable source section containing a source title or domain and a clickable URL. Inline citation interactions must open only a valid, same-message indexed source; invalid indices must remain inert and not point to unrelated sources.

Keep `backend/services/orchestration_service.py` as the structured-source producer, but add contract coverage proving every emitted web-search source includes a non-empty URL and stable ordering. Update the manual script to require a source list or clickable source panel, not merely numeric markers in assistant prose.

#### Expected File Tree After Phase 4

This tree is cumulative with Phases 1 through 3.

```text
backend/services/
└── orchestration_service.py                                  [modified]
frontend/src/components/Citations/
└── index.tsx                                                  [modified]
frontend/src/components/MessageList/
└── MessageItem.tsx                                            [modified]
frontend/src/services/chat/
└── index.ts                                                    [modified]
frontend/src/utils/
└── exportChat.ts                                               [new]
tests/backend/
└── test_perplexity_node.py                                    [modified]
tests/frontend/components/MessageList/
└── citations.test.ts                                          [modified]
tests/frontend/utils/
└── exportChat.test.ts                                         [new]
docs/worklog/202607/2026_07_17_experiment/
└── test_script_new.md                                          [modified]
```

#### Work List

Audit follow-up note: Items 1, 4, and 5 were not fully satisfied by the original `41c0171^..cc77ca4` range. They are completed by follow-up commit `3c75855`. Items 2 and 3 were primarily verified as pre-existing stream/UI behavior and are now covered by the added citation component tests.

1. [x] Modify `backend/services/orchestration_service.py`.
   - [x] Validate the source records built by `OrchestrationService._node_perplexity_search()` before emitting `event: sources`; omit malformed records rather than emitting a source without a URL.
   - [x] Preserve source ordering so citation index `n` has a deterministic mapping to source record `n`.
2. [x] Modify `frontend/src/services/chat/index.ts`.
   - [x] Update each stream completion path that builds `messageData` to retain only the current request's structured `sources` payload.
   - [x] Clear stale source state on stream cancellation, failure, or a new request before a completion callback can persist it.
3. [x] Modify `frontend/src/components/MessageList/MessageItem.tsx` and `frontend/src/components/Citations/index.tsx`.
   - [x] Render a source section for every assistant message that has structured sources, with a readable source title or domain and a safe external URL action.
   - [x] Update indexed citation opening so it accepts only an in-range source index for the same message; do not infer a source from model prose alone.
4. [x] Extend `tests/backend/test_perplexity_node.py`.
   - [x] Assert `event: sources` includes stable ordered title and non-empty URL fields for valid search results.
   - [x] Assert malformed search records do not produce a clickable source payload.
5. [x] Extend `tests/frontend/components/MessageList/citations.test.ts`.
   - [x] Add a sourced assistant-message case that renders source title/domain and an external URL.
   - [x] Add an inline-citation case that opens the correct source and an out-of-range marker case that does not open any source.
6. [x] Add citation-preserving transcript export in `frontend/src/utils/exportChat.ts` and `tests/frontend/utils/exportChat.test.ts`.
   - [x] Export source title/domain and URL in Markdown and DOCX output.
   - [x] Verify exported transcripts retain the same structured source mapping.
7. [x] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_new.md`.
   - [x] Require Act 02 to capture the visible source title/domain and URL for every checked marker.
   - [x] Mark marker-only output without a source list or clickable mapping as a failure.

#### Test Plan

Mock a web-search result set with valid and malformed records in the backend node tests. In frontend tests, feed a persisted assistant message containing both prose markers and structured sources; assert the source panel is visible and each URL is safe. Add a stream-client/service test if existing coverage cannot prove that the `sources` event reaches persisted `messageData`.

```bash
./backend/.venv/bin/python -m pytest -q tests/backend/test_perplexity_node.py
npm run test:frontend -- --run tests/frontend/components/MessageList/citations.test.ts
```

#### Expected Output / Result

Every visible search citation has an observable source name or domain and a clickable URL from the structured source payload. A numeric marker without a corresponding structured source is not treated as verified. Source ordering is stable from the search SSE event through the persisted message and rendered UI.

#### Testing Script

##### Act 01: Verify Search Sources

Ask a current-information question that activates web search and wait for the completed response.

Pass condition: the response exposes a source list or panel where each checked citation index maps to a title/domain and clickable URL.

##### Act 02: Reject an Unmapped Citation Marker

Use a deterministic mocked streamed response containing a numeric citation marker but no structured sources.

Pass condition: the UI does not display the marker as a verifiable source and automated coverage records the contract violation.

#### Gate to Enter the Next Phase

Run both commands above, `npm run lint --prefix frontend`, `npm run typecheck --prefix frontend`, and `git diff --check`. Retain both a screenshot and an exported transcript showing source title/domain and URL mapping for Act 01. Do not proceed if sources are lost after streaming, persistence, rendering, or transcript export; if stale sources appear on another message; if an invalid marker opens a source; or if a link lacks safe external-link handling.

#### Phase Commit

Create one phase commit after the gate passes:

```text
fix(search): preserve verifiable source citations
```

Inspect `git status --short`, then stage only the listed backend, frontend, test, and Act 02 script paths/hunks. Run `git diff --cached --check` and `git diff --cached --stat`, commit, and confirm with `git show --stat --oneline --summary HEAD`. Keep unrelated frontend changes unstaged.

### Phase 5: Add ComPeer Preflight Tracing and Deterministic Recovery Validation

#### Problem

The available Act 09 and Act 10 artifacts cannot establish whether either scenario was executed or what result it produced. Act 09 lacks `T0`, trigger state, cooldown, inactivity and scroll thresholds, scheduler execution, importance-gate result, task ID, mailbox-task state, and delivery events. Act 10 lacks a Redis timeout, reconciliation, worker, task, and mailbox trace. In addition, the Act 09 log predates Act 08 even though the script requires Act 08 before Act 09. The phase must create reproducible evidence rather than assume a delivery failure or a blocked recovery scenario.

#### Assumptions

Redis remains an acceleration queue, while `mailbox_delayed_tasks` is the durable delivery-intent store when the database is enabled. A mailbox message is delivered only after durable persistence; WebSocket notification failure must not reverse delivery. Production logs must not contain raw hot-memory snapshots, event summaries, generated letter text, or user content.

#### Solution

Introduce a small server-owned preflight result for each proactive scheduling attempt and emit one safe correlated event describing whether the user is eligible or blocked. Add an explicit `mailbox.delivered` event after durable mail persistence, plus safe reconciliation events. Preserve existing worker and scheduler behavior, but test the full transition using deterministic hot-memory/clock fixtures and a durable task seeded for recovery rather than waiting for model-driven eligibility.

#### Implementation

> Context: Add Google-style docstrings to the proposed preflight result type, evaluator, and materially changed scheduler/worker methods. Document why eligibility is computed once for observability, why a task ID is the correlation boundary, why Redis failure cannot erase durable intent, and why logs intentionally omit raw user or model text. Add inline comments only at trigger-clearing, cooldown-setting, lease-claim, and exactly-once delivery transitions to explain their ordering constraints.

Modify `backend/services/compeer_scheduler.py` to add a proposed `ProactivePreflight` data type and `evaluate_proactive_preflight()` helper. It should collect safe booleans/counts for trigger presence, cooldown, inactivity threshold, scroll threshold, importance result, existing-pending-task status, and scheduling result. `_process_proactive_user()` must emit `compeer.preflight_evaluated` at `INFO` before scheduling and `compeer.preflight_blocked` at `INFO` when an eligibility condition prevents scheduling. It must retain the existing rule that `trigger_proactive` is cleared only after a durable task ID exists.

Modify `backend/mailbox_store.py` to log `mailbox.delivered` after `mark_delayed_task_delivered()` succeeds, and log safe reconciliation counts when `restore_delayed_queue_from_db()` restores due work. On delivery failure, retain the current failure transition and ensure `mailbox.retryable_failed` or `mailbox.terminal_failed` identifies the same task ID according to the store's retry outcome. Do not log mail subject or content.

Extend scheduler and worker tests for each preflight branch and the complete durable state transition. Update the manual Act 09 to collect only user-journey evidence before the wait window. Move Redis timeout recovery entirely to deterministic unit/integration coverage: seed a durable task, simulate enqueue failure, run reconciliation and the worker twice, and prove exactly one delivery without asking a manual tester to perform fault injection.

#### Expected File Tree After Phase 5

This tree is cumulative with Phases 1 through 4.

```text
backend/
├── mailbox_store.py                                           [modified]
└── services/
    └── compeer_scheduler.py                                  [modified]
tests/backend/
├── test_compeer_scheduler.py                                 [modified]
├── test_delayed_mail_worker.py                               [modified]
└── test_mailbox_flow.py                                      [modified]
docs/worklog/202607/2026_07_17_experiment/
└── test_script_new.md                                         [modified]
```

#### Work List

Audit follow-up note: The mailbox-store delivery/reconciliation behavior listed here existed before the audited `41c0171^..cc77ca4` range. Follow-up commit `438bbda` adds the missing safe lifecycle metadata and deterministic assertions without changing the mailbox delivery contract.

1. [x] Modify `backend/services/compeer_scheduler.py`.
   - [x] Add the proposed `ProactivePreflight` type and `evaluate_proactive_preflight()` helper for `_process_proactive_user()`.
   - [x] Emit `compeer.preflight_evaluated` with safe booleans/counts, user ID, scheduler iteration correlation ID, and task ID when created.
   - [x] Emit `compeer.preflight_blocked` with a stable safe reason code for cooldown, inactivity, insufficient scroll evidence, failed importance gate, existing pending task, or absent trigger.
   - [x] Preserve trigger clearing and cooldown writes after, never before, durable scheduling returns a task ID.
2. [x] Modify `backend/mailbox_store.py`.
   - [x] Update `run_delayed_mail_iteration()` to emit `mailbox.claimed`, `mailbox.delivered`, and a safe failure event with the same task ID across each transition.
   - [x] Update `MailboxStore.restore_delayed_queue_from_db()` to emit a reconciliation event with restored-task count and no payload content.
   - [x] Preserve exactly-once behavior when the worker is rerun after a completed delivery.
3. [x] Extend `tests/backend/test_compeer_scheduler.py`.
   - [x] Add deterministic preflight tests for trigger absent, cooldown blocked, inactivity blocked, insufficient-scroll blocked, importance blocked, pending-task blocked, and eligible scheduling.
   - [x] Assert structured preflight logs contain safe metadata only and that a durable scheduling failure preserves the trigger for retry.
4. [x] Extend `tests/backend/test_delayed_mail_worker.py` and `tests/backend/test_mailbox_flow.py`.
   - [x] Assert one task produces ordered `scheduled`, `claimed`, and `delivered` events with one task ID.
   - [x] Simulate Redis enqueue failure after durable DB insertion, restore the queue, run the worker twice, and assert exactly one persisted mail.
   - [x] Assert notification failure does not revert durable delivery and retry/terminal failure events preserve safe task correlation.
5. [x] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_new.md`.
   - [x] Replace the engineering-heavy script with the user-journey `test_script_new.md`: retain visible memory, citation, edit/delete, and mailbox behavior only.
   - [x] Require the manual Act 09 to record `T0` and mailbox snapshots at 120 and 150 seconds; request backend correlation only after a visible failure.
   - [x] Keep Redis timeout, reconciliation, and exactly-once assertions exclusively in `tests/backend/test_delayed_mail_worker.py` and `tests/backend/test_mailbox_flow.py`.

#### Test Plan

Use isolated fake Redis, mailbox-store, and clock fixtures. Scheduler tests must prove every eligibility branch emits one safe preflight result and that one failing user does not prevent subsequent users from being processed. Worker tests must prove a database-backed task survives Redis enqueue failure, is claimed once, is delivered once, and remains delivered when the worker repeats. Capture `caplog` output and assert event names/task IDs rather than free-form messages.

```bash
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_compeer_scheduler.py \
  tests/backend/test_delayed_mail_worker.py \
  tests/backend/test_mailbox_flow.py \
  tests/backend/test_mailbox_store.py
```

#### Expected Output / Result

The manual Act 09 establishes the user-visible mailbox experience with a recorded timing boundary. Scheduler and worker tests establish the internal preflight, queue recovery, claim, delivery, notification-failure, and exactly-once guarantees with correlated task IDs. Redis recovery is verified without a manual tester.

#### Testing Script

##### Act 01: Verify Manual Mailbox Delivery

For a clean test account, use the manual script's normal reading and scrolling journey, record `T0`, and retain mailbox snapshots at 120 and 150 seconds.

Pass condition: exactly one appropriate ComPeer message appears in the mailbox by the stated deadline, without being inserted into chat.

##### Act 02: Verify Deterministic Redis Recovery in Automation

Run the Redis enqueue-failure integration tests with a seeded durable task, reconciliation, and two worker iterations.

Pass condition: one task is restored and exactly one mailbox message is persisted; the second worker iteration produces no duplicate.

#### Gate to Enter the Next Phase

Run the focused command above and retain output plus safe event traces for one successful delivery and one recovery delivery. Run `git diff --check`. Execute the manual mailbox Act on a clean account and the Redis-recovery Act through automated tests. Do not declare the phase complete if any preflight branch lacks a reason, a scheduled task lacks task correlation, a task misses the delivery deadline without a retry/terminal event, the manual Act lacks `T0`/mailbox evidence, or a second worker run creates another message.

#### Phase Commit

Create one phase commit after the gate passes:

```text
feat(compeer): trace proactive delivery and recovery
```

Inspect `git status --short`, then stage only the scheduler, mailbox, focused test, and Act 09/10 script paths/hunks. Run `git diff --cached --check` and `git diff --cached --stat`, commit, and confirm with `git show --stat --oneline --summary HEAD`. Do not include report-only files or unrelated worktree changes.

### Cross-Phase Regression and Final Acceptance

After all five phase commits exist, run the complete backend suite and the repository-defined frontend test commands:

```bash
./backend/.venv/bin/python -m pytest -q tests/backend
npm run test:frontend
npm run lint --prefix frontend
npm run typecheck --prefix frontend
npm run build
```

Rerun `test_script_new.md` against fresh, isolated accounts. Acceptance requires: no unsupported ability, anxiety, understanding, mastery, or progress claim and no forbidden durable memory in Acts 01 and 02; no new memory from the Act 03 question; correct visible candidate/promotion behavior in Acts 04 and 05; a completed temporary-goal experience in Act 06; a visible explicit preference in Act 07; successful edit/delete reload behavior in Act 08; visible source mapping in Act 02; and one time-bounded ComPeer mailbox experience in Act 09. Separately, the Phase 5 automated suite must prove Redis recovery and exactly-once delivery. Missing required evidence is an incomplete acceptance run, never a pass.

Remaining operational risks are external search availability, model-driven proactive eligibility, Redis availability, browser persistence behavior, and false positives from response-boundary validation. The plan mitigates them through fail-closed source mapping, durable mailbox tasks, deterministic recovery tests, safe structured events, explicit manual preflight capture, and deterministic response-guard tests. Before handoff, run `git status --short` and inspect the phase commits to prove the completed work is committed and no planned change remains uncommitted. No push or deployment is included in this plan.
