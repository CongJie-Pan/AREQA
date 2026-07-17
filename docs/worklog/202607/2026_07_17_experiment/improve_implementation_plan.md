# 2026-07-17 Experiment Improvement Implementation Plan

This plan addresses the failures and evidence gaps documented in the 17 July experiment report. The phases are ordered by dependency and risk: repair the confirmed profile-edit failure first; then make memory lifecycle assertions observable; then make web citations verifiable at the user boundary; and finally make ComPeer eligibility and delivery diagnosable and reproducible. Each phase is independently testable and committed only after its gate passes.

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
└── test_script_2025_07_17.md                                 [modified]
```

#### Work List

1. [ ] Modify `backend/main.py`.
   - [ ] Add the proposed `_update_explicit_profile_memory()` helper adjacent to `_delete_explicit_profile_memory()`.
   - [ ] Update `edit_memory_endpoint()` to call the helper for `profile:explicit:` IDs and remove its local `import json` statements.
   - [ ] Preserve a durable profile update when `MemoryStore.update_working_memory()` raises, while emitting `memory.correction_sync_failed` with safe metadata only.
   - [ ] Emit `memory.correction_applied` only after the profile write succeeds; return a non-success response for an unknown explicit memory ID.
2. [ ] Extend `tests/backend/test_gum_endpoints.py`.
   - [ ] Add a regression for `PUT /api/v1/memory/profile:explicit:<id>` that asserts HTTP 2xx, changed `explicit_memories`, and a successful reload from the mocked store.
   - [ ] Add a test that a working-memory synchronization exception is logged safely and does not undo the persisted profile edit.
   - [ ] Add a not-found test for an explicit memory ID that does not belong to the authenticated profile.
3. [ ] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_2025_07_17.md`.
   - [ ] Replace Act 08 with Act 08A for edit/reload verification and Act 08B for delete/reload verification.
   - [ ] Require recording endpoint, HTTP status, memory ID, safe error code, and refresh result; prohibit Act 08B after an Act 08A failure.

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

Inspect `git status --short` and preserve unrelated changes. Stage only `backend/main.py`, `tests/backend/test_gum_endpoints.py`, and the Act 08 section of `docs/worklog/202607/2026_07_17_experiment/test_script_2025_07_17.md`. Run `git diff --cached --check` and `git diff --cached --stat`, then commit. Confirm with `git show --stat --oneline --summary HEAD` before Phase 2. Do not amend, rewrite, or push existing commits.

### Phase 2: Make Memory-Governance Evidence Verifiable

#### Problem

Acts 01, 04, 05, 06, and 07 produced useful decision logs, but the run did not prove the required durable state. It did not record candidate status, expiration, final evidence counts, unique conversation/message counts, or profile counts. Consequently, the experiment cannot distinguish safe deduplication from an unintended new candidate or prove that GUM-derived anxiety, ability, interest, and one-off search context remained out of cold/profile storage.

#### Assumptions

`MemoryStore` remains the authoritative owner of cold candidates, verified profile memory, and promotion invariants. The product memory page must continue to hide candidates and operational state from ordinary users. Manual validation can use authenticated engineering access to the same test account's backing store; no public API that exposes candidate evidence or sensitive data will be added.

#### Solution

Strengthen safe lifecycle observability at the storage boundary and make the manual script require a read-only, test-account-only state snapshot. Storage events will carry counts, IDs, categories, status, and reason codes, but never raw evidence or model output. The script will record the backing-store snapshot separately, with evidence text redacted from the report artifact where it is unnecessary.

#### Implementation

> Context: Add Google-style docstrings to materially changed memory-store and ingestion methods. Document why candidate evidence remains internal, why log metadata is count-and-ID based, why one conversation cannot corroborate a passive preference twice, and why incomplete or model-derived data fails closed. Add inline comments only at duplicate-evidence and promotion-state transitions to explain the invariant being preserved.

Modify `backend/memory_store.py` so `append_cold_candidate()` emits a safe event after its transaction commits. The event must distinguish `evidence_appended`, `duplicate_message_ignored`, and `duplicate_conversation_ignored`, including candidate ID, category, candidate status, evidence count, distinct conversation count, and correlation IDs. Update `promote_cold_candidate()` and temporary-goal completion paths to include lifecycle status and independent-evidence counts in their existing safe events. Do not alter the existing eligibility or promotion thresholds merely to satisfy logging.

Modify `backend/services/memory_ingestion_service.py` to pass the safe correlation fields through its terminal decision events and to report a candidate snapshot reference after canonical matching or promotion. Extend regression tests around store state, not only log strings. Update the manual script with a standard pre-Act snapshot, post-Act snapshot, and cleanup record; list the exact fields an engineer must inspect from cold candidates, verified profile, working memory, and mailbox state.

#### Expected File Tree After Phase 2

This tree is cumulative with Phase 1.

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
└── test_script_2025_07_17.md                                 [modified]
```

#### Work List

1. [ ] Modify `backend/memory_store.py`.
   - [ ] Update `MemoryStore.append_cold_candidate()` to emit one safe post-transaction evidence event with candidate ID, category, status, evidence count, distinct conversation count, and duplicate reason when applicable.
   - [ ] Update `MemoryStore.promote_cold_candidate()` to include independent-evidence counts and lifecycle status in `memory.profile_promoted` and `memory.promotion_blocked` events.
   - [ ] Update the temporary-goal completion path to emit completed status and the safe working-memory keys cleared, without message content.
2. [ ] Modify `backend/services/memory_ingestion_service.py`.
   - [ ] Update `MemoryIngestionService.ingest_user_evidence()` terminal logs to carry message ID, conversation ID, candidate ID when available, category, state, and reason code only.
   - [ ] Preserve the rule that semantic analysis is advisory and cannot authorize a profile write or append evidence for rejected input.
3. [ ] Extend `tests/backend/test_memory_store.py`.
   - [ ] Add assertions that a same-conversation repeat and a duplicate message ID leave candidate evidence and distinct-conversation counts unchanged.
   - [ ] Add assertions that expired, completed, cross-user, and wrong-category candidates cannot be promoted or merged.
4. [ ] Extend `tests/backend/test_memory_ingestion_service.py` and `tests/backend/test_memory_injection_regression.py`.
   - [ ] Assert that sensitive content, one-off SpaceX context, and GUM/model inference do not create cold or profile records.
   - [ ] Assert that the equivalent-preference pair creates one canonical candidate and exactly one profile entry after two distinct conversations.
   - [ ] Capture structured logs and assert that they include safe counts and identifiers but not raw user text, evidence quotes, sensitive labels, or model output.
5. [ ] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_2025_07_17.md`.
   - [ ] Add a pre-Act and post-Act state-record template for cold candidate count, profile count, category, status, expiry/completion, evidence message IDs, and conversation IDs.
   - [ ] Add explicit forbidden-record checks for sensitive, ability, anxiety, interest, and one-off search-context records in Acts 01 and 02.
   - [ ] Add Act 05 assertions for one candidate, one profile memory, two independent conversations, two independent messages, and no count change on replay.
   - [ ] Add cleanup requirements for hot memory, candidates, profile entries, cooldowns, mailbox tasks, and test labels.

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

##### Act 03: Verify Independent Preference Corroboration

Send the two equivalent preference declarations in distinct conversations, then replay one declaration in the second conversation and replay its message ID.

Pass condition: one candidate and one profile memory exist with exactly two distinct conversation IDs and two distinct message IDs; both replays leave counts unchanged.

#### Gate to Enter the Next Phase

Run the focused command above and retain output plus a redacted test-account state snapshot. Run `git diff --check`. Execute the three Acts against a clean account and retain safe event names, candidate/profile counts, category/status, and distinct-ID counts. Do not proceed if a forbidden durable record exists, a replay changes corroboration counts, a required field is missing, or logs reveal raw evidence.

#### Phase Commit

Create one phase commit after the gate passes:

```text
test(memory): make governance lifecycle evidence auditable
```

Inspect `git status --short` first. Stage only `backend/memory_store.py`, `backend/services/memory_ingestion_service.py`, the three named memory test files, and the Phase 2 test-script hunks. Run `git diff --cached --check` and `git diff --cached --stat`, commit, and verify with `git show --stat --oneline --summary HEAD`. Do not stage unrelated experiment artifacts or prior report files.

### Phase 3: Make Search Citations Verifiable in the User Interface

#### Problem

Act 02 showed inline numeric citation markers, but the saved transcript did not contain a source name, URL, or observable mapping from marker to source. The backend already emits structured `sources` events with title, URL, snippet, and score, and the frontend has a citation component. The missing acceptance evidence indicates that source payload preservation or its visible presentation is not guaranteed end to end.

#### Assumptions

The source payload may contain untrusted external URLs and titles. The frontend must continue to use safe external-link attributes and must not manufacture citations when search produced no source payload. Citation markers in model text are not independently trustworthy; they are only navigational affordances when a same-message structured source collection exists.

#### Solution

Treat structured source payload as the authority. Preserve it from the SSE `sources` event to the persisted assistant message, render a visible source list with title/domain and URL affordance for every sourced answer, and disable inline marker interaction when the corresponding indexed source is absent. Keep the backend payload contract stable and add end-to-end tests that fail if a response retains markers but loses sources.

#### Implementation

> Context: Add Google-style docstrings or TSDoc to materially changed source-payload handling functions and components. Document why structured sources, rather than model-authored marker text, are authoritative; why an absent mapping must fail closed in the UI; and why external URLs require existing safe-link handling. Use inline comments only where stream completion attaches sources to the persisted message or where indexed marker lookup rejects an invalid mapping.

Modify `frontend/src/services/chat/index.ts` so each streaming execution path attaches the structured `sources` payload to the same assistant message before persistence and clears per-request source state when a stream is cancelled or fails. Modify `frontend/src/components/MessageList/MessageItem.tsx` and `frontend/src/components/Citations/index.tsx` so a message with structured sources shows a visible, expandable source section containing a source title or domain and a clickable URL. Inline citation interactions must open only a valid, same-message indexed source; invalid indices must remain inert and not point to unrelated sources.

Keep `backend/services/orchestration_service.py` as the structured-source producer, but add contract coverage proving every emitted web-search source includes a non-empty URL and stable ordering. Update the manual script to require a source list or clickable source panel, not merely numeric markers in assistant prose.

#### Expected File Tree After Phase 3

This tree is cumulative with Phases 1 and 2.

```text
backend/services/
└── orchestration_service.py                                  [modified]
frontend/src/components/Citations/
└── index.tsx                                                  [modified]
frontend/src/components/MessageList/
└── MessageItem.tsx                                            [modified]
frontend/src/services/chat/
└── index.ts                                                    [modified]
tests/backend/
└── test_perplexity_node.py                                    [modified]
tests/frontend/components/MessageList/
└── citations.test.ts                                          [modified]
docs/worklog/202607/2026_07_17_experiment/
└── test_script_2025_07_17.md                                  [modified]
```

#### Work List

1. [ ] Modify `backend/services/orchestration_service.py`.
   - [ ] Validate the source records built by `OrchestrationService._node_perplexity_search()` before emitting `event: sources`; omit malformed records rather than emitting a source without a URL.
   - [ ] Preserve source ordering so citation index `n` has a deterministic mapping to source record `n`.
2. [ ] Modify `frontend/src/services/chat/index.ts`.
   - [ ] Update each stream completion path that builds `messageData` to retain only the current request's structured `sources` payload.
   - [ ] Clear stale source state on stream cancellation, failure, or a new request before a completion callback can persist it.
3. [ ] Modify `frontend/src/components/MessageList/MessageItem.tsx` and `frontend/src/components/Citations/index.tsx`.
   - [ ] Render a source section for every assistant message that has structured sources, with a readable source title or domain and a safe external URL action.
   - [ ] Update indexed citation opening so it accepts only an in-range source index for the same message; do not infer a source from model prose alone.
4. [ ] Extend `tests/backend/test_perplexity_node.py`.
   - [ ] Assert `event: sources` includes stable ordered title and non-empty URL fields for valid search results.
   - [ ] Assert malformed search records do not produce a clickable source payload.
5. [ ] Extend `tests/frontend/components/MessageList/citations.test.ts`.
   - [ ] Add a sourced assistant-message case that renders source title/domain and an external URL.
   - [ ] Add an inline-citation case that opens the correct source and an out-of-range marker case that does not open any source.
6. [ ] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_2025_07_17.md`.
   - [ ] Require Act 02 to capture the visible source title/domain and URL for every checked marker.
   - [ ] Mark marker-only output without a source list or clickable mapping as a failure.

#### Test Plan

Mock a web-search result set with valid and malformed records in the backend node tests. In frontend tests, feed a persisted assistant message containing both prose markers and structured sources; assert the source panel is visible and each URL is safe. Add a stream-client/service test if existing coverage cannot prove that the `sources` event reaches persisted `messageData`.

```bash
./backend/.venv/bin/python -m pytest -q tests/backend/test_perplexity_node.py
npm run test -- --runInBand tests/frontend/components/MessageList/citations.test.ts
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

Run both commands above, the applicable frontend lint/typecheck command from `package.json`, and `git diff --check`. Retain a screenshot or transcript showing source title/domain and URL mapping for Act 01. Do not proceed if sources are lost after streaming, stale sources appear on another message, an invalid marker opens a source, or a link lacks safe external-link handling.

#### Phase Commit

Create one phase commit after the gate passes:

```text
fix(search): preserve verifiable source citations
```

Inspect `git status --short`, then stage only the listed backend, frontend, test, and Act 02 script paths/hunks. Run `git diff --cached --check` and `git diff --cached --stat`, commit, and confirm with `git show --stat --oneline --summary HEAD`. Keep unrelated frontend changes unstaged.

### Phase 4: Add ComPeer Preflight Tracing and Deterministic Recovery Validation

#### Problem

Act 09 did not yield a user-visible ComPeer message within the required window, but the artifacts cannot identify why. They omit the trigger flag, cooldown state, inactivity threshold, scroll threshold, scheduler execution, importance-gate result, task ID, mailbox task state, and delivery events. Act 10 was blocked because it depended on this nondeterministic normal-flow Act, even though the delayed-mail worker already has a recoverable durable-task design.

#### Assumptions

Redis remains an acceleration queue, while `mailbox_delayed_tasks` is the durable delivery-intent store when the database is enabled. A mailbox message is delivered only after durable persistence; WebSocket notification failure must not reverse delivery. Production logs must not contain raw hot-memory snapshots, event summaries, generated letter text, or user content.

#### Solution

Introduce a small server-owned preflight result for each proactive scheduling attempt and emit one safe correlated event describing whether the user is eligible or blocked. Add an explicit `mailbox.delivered` event after durable mail persistence, plus safe reconciliation events. Preserve existing worker and scheduler behavior, but test the full transition using deterministic hot-memory/clock fixtures and a durable task seeded for recovery rather than waiting for model-driven eligibility.

#### Implementation

> Context: Add Google-style docstrings to the proposed preflight result type, evaluator, and materially changed scheduler/worker methods. Document why eligibility is computed once for observability, why a task ID is the correlation boundary, why Redis failure cannot erase durable intent, and why logs intentionally omit raw user or model text. Add inline comments only at trigger-clearing, cooldown-setting, lease-claim, and exactly-once delivery transitions to explain their ordering constraints.

Modify `backend/services/compeer_scheduler.py` to add a proposed `ProactivePreflight` data type and `evaluate_proactive_preflight()` helper. It should collect safe booleans/counts for trigger presence, cooldown, inactivity threshold, scroll threshold, importance result, existing-pending-task status, and scheduling result. `_process_proactive_user()` must emit `compeer.preflight_evaluated` at `INFO` before scheduling and `compeer.preflight_blocked` at `INFO` when an eligibility condition prevents scheduling. It must retain the existing rule that `trigger_proactive` is cleared only after a durable task ID exists.

Modify `backend/mailbox_store.py` to log `mailbox.delivered` after `mark_delayed_task_delivered()` succeeds, and log safe reconciliation counts when `restore_delayed_queue_from_db()` restores due work. On delivery failure, retain the current failure transition and ensure `mailbox.retryable_failed` or `mailbox.terminal_failed` identifies the same task ID according to the store's retry outcome. Do not log mail subject or content.

Extend scheduler and worker tests for each preflight branch and the complete durable state transition. Update Act 09 to collect preflight state before the wait window. Replace Act 10's dependency on Act 09 with a clean-account deterministic task seeding procedure that simulates Redis enqueue failure, runs reconciliation, runs the worker twice, and proves exactly one delivery.

#### Expected File Tree After Phase 4

This tree is cumulative with Phases 1 through 3.

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
└── test_script_2025_07_17.md                                 [modified]
```

#### Work List

1. [ ] Modify `backend/services/compeer_scheduler.py`.
   - [ ] Add the proposed `ProactivePreflight` type and `evaluate_proactive_preflight()` helper for `_process_proactive_user()`.
   - [ ] Emit `compeer.preflight_evaluated` with safe booleans/counts, user ID, scheduler iteration correlation ID, and task ID when created.
   - [ ] Emit `compeer.preflight_blocked` with a stable safe reason code for cooldown, inactivity, insufficient scroll evidence, failed importance gate, existing pending task, or absent trigger.
   - [ ] Preserve trigger clearing and cooldown writes after, never before, durable scheduling returns a task ID.
2. [ ] Modify `backend/mailbox_store.py`.
   - [ ] Update `run_delayed_mail_iteration()` to emit `mailbox.claimed`, `mailbox.delivered`, and a safe failure event with the same task ID across each transition.
   - [ ] Update `MailboxStore.restore_delayed_queue_from_db()` to emit a reconciliation event with restored-task count and no payload content.
   - [ ] Preserve exactly-once behavior when the worker is rerun after a completed delivery.
3. [ ] Extend `tests/backend/test_compeer_scheduler.py`.
   - [ ] Add deterministic preflight tests for trigger absent, cooldown blocked, inactivity blocked, insufficient-scroll blocked, importance blocked, pending-task blocked, and eligible scheduling.
   - [ ] Assert structured preflight logs contain safe metadata only and that a durable scheduling failure preserves the trigger for retry.
4. [ ] Extend `tests/backend/test_delayed_mail_worker.py` and `tests/backend/test_mailbox_flow.py`.
   - [ ] Assert one task produces ordered `scheduled`, `claimed`, and `delivered` events with one task ID.
   - [ ] Simulate Redis enqueue failure after durable DB insertion, restore the queue, run the worker twice, and assert exactly one persisted mail.
   - [ ] Assert notification failure does not revert durable delivery and retry/terminal failure events preserve safe task correlation.
5. [ ] Modify `docs/worklog/202607/2026_07_17_experiment/test_script_2025_07_17.md`.
   - [ ] Add an Act 09 preflight record for trigger flag, cooldown, last interaction, scroll count, importance result, scheduler iteration, pending task, and task ID before `T0 + 120` seconds.
   - [ ] Require a correlated `scheduled -> claimed -> delivered` trace or a correlated retryable/terminal failure by `T0 + 150` seconds.
   - [ ] Make Act 10 independent: seed one clean durable delayed-mail task, simulate Redis timeout, restore Redis, reconcile, run the worker twice, and record one delivered mail.

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

Act 09 can distinguish ineligible scheduling from durable scheduling, queue recovery, worker claim, delivery, and notification failure using one task ID. Act 10 can run independently of model behavior and demonstrate durable recovery plus exactly-once mailbox delivery after a simulated Redis failure.

#### Testing Script

##### Act 01: Record ComPeer Preflight

For a clean test account, create the intended trigger state and record preflight output before waiting: trigger presence, cooldown, inactivity, scroll count, importance result, existing task ID, and scheduler iteration ID.

Pass condition: the preflight output states either one explicit block reason or one newly scheduled task ID.

##### Act 02: Verify Normal Delayed Delivery

When Act 01 returns a task ID, record `T0`, wait to the configured delivery window, and inspect the mailbox task and user inbox.

Pass condition: the same task ID has `scheduled`, `claimed`, and `delivered` events and exactly one visible mailbox message by the deadline.

##### Act 03: Verify Redis-Recovery Delivery

With another clean account, seed one durable delayed-mail task, simulate Redis enqueue timeout, restore Redis, reconcile the queue, and run the worker twice.

Pass condition: one task is restored and exactly one mailbox message is persisted; the second worker iteration produces no duplicate.

#### Gate to Enter the Next Phase

Run the focused command above and retain output plus safe event traces for one successful delivery and one recovery delivery. Run `git diff --check`. Execute all three Acts on isolated accounts. Do not declare the phase complete if any preflight branch lacks a reason, a scheduled task lacks task correlation, a task misses the delivery deadline without a retry/terminal event, or a second worker run creates another message.

#### Phase Commit

Create one phase commit after the gate passes:

```text
feat(compeer): trace proactive delivery and recovery
```

Inspect `git status --short`, then stage only the scheduler, mailbox, focused test, and Act 09/10 script paths/hunks. Run `git diff --cached --check` and `git diff --cached --stat`, commit, and confirm with `git show --stat --oneline --summary HEAD`. Do not include report-only files or unrelated worktree changes.

### Cross-Phase Regression and Final Acceptance

After all four phase commits exist, run the complete backend suite and the frontend test/typecheck commands defined by the repository:

```bash
./backend/.venv/bin/python -m pytest -q tests/backend
npm run test:backend
npm run test
npm run lint
npm run typecheck
```

If an npm command is not defined, record that fact and run the closest repository-defined equivalent from `package.json`; do not silently skip frontend validation. Rerun the revised manual script against fresh, isolated accounts. Acceptance requires: no forbidden durable memory from Acts 01 and 02; deterministic candidate/evidence counts in Acts 04 and 05; a completed temporary-goal lifecycle in Act 06; a safe explicit promotion in Act 07; successful dependent Act 08A/08B; verifiable source mapping in Act 02; a correlated successful ComPeer delivery in Act 09; and exactly-once Redis-recovery delivery in Act 10.

Remaining operational risks are external search availability, model-driven proactive eligibility, Redis availability, and browser persistence behavior. The plan mitigates them through fail-closed source mapping, durable mailbox tasks, deterministic recovery tests, safe structured events, and explicit manual preflight capture. Before handoff, run `git status --short` and `git log --oneline -4` to prove the four ordered phase commits exist and no planned change remains uncommitted. No push or deployment is included in this plan.
