# ComPeer Behavior-Signal Scheduler Fix Implementation Plan

This plan fixes the Act 09 failure documented in `docs/worklog/202607/2026_07_18_experiment/experiment_report.md`. The current evidence indicates that ComPeer did not fail at mailbox delivery; it failed before scheduling because frontend scroll telemetry is written to `behavior_signals`, while the proactive scheduler fallback still counts legacy `hot_memory` `obs_*` entries. The phase order is dependency-based: first repair the scheduler data path, then add terminal observability and timing clarity, then update regression coverage and the manual validation contract.

### Phase 1: Make ComPeer Scheduler Consume Behavior Signals

#### Problem

Act 09 expected one ComPeer mailbox message after normal reading and scrolling, but backend preflight logs showed `trigger_present=False`, `scroll_count=0`, `scheduling_succeeded=None`, `task_id=none`, and `reason=absent_trigger`. Code review shows that `/api/v1/log_action` persists scroll telemetry through `MemoryStore.append_behavior_signal()` to `areqa:behavior_signals:{user_id}`, while `_process_proactive_user()` in `backend/services/compeer_scheduler.py` still scans `hot_memory` keys named `obs_*`. The scheduler therefore cannot see current frontend scroll telemetry.

#### Assumptions

- Scroll, focus, blur, and similar client telemetry must remain out of prompt-visible hot memory.
- `MemoryStore.get_behavior_signals(user_id)` is the intended read API for frontend telemetry.
- The existing minimum behavior evidence threshold is six scroll signals.
- Existing explicit trigger and avatar summon behavior must remain unchanged.
- If `behavior_signals` timestamps are malformed or missing, those entries must not crash the scheduler; they should be ignored or treated conservatively.
- If the product later decides that normal scroll should not trigger ComPeer, this phase should be reverted or guarded by configuration. Under the current experiment contract, normal read/scroll is expected to be eligible input.

#### Solution

Move the behavior-derived ComPeer fallback from legacy hot-memory observation keys to the behavior-signal store. `_process_proactive_user()` should read recent behavior signals through `store.get_behavior_signals(user_id)`, count recent `type == "scroll"` entries, preserve the existing threshold of six scroll signals, and only then call the current LLM proactive-event detector and importance gate. This keeps telemetry out of prompt memory while making the scheduler consume the same data path that the frontend writes.

The phase must also define a safe consumption path for used scroll signals. Once behavior-derived scheduling succeeds or reaches a terminal accepted state, the scheduler should remove or mark the consumed scroll signals so the same batch does not repeatedly schedule ComPeer messages.

#### Implementation

> Context: Add or update Google-style docstrings for every new or materially changed public helper. Document why ComPeer reads from `behavior_signals` instead of hot memory, the privacy boundary that keeps UI telemetry out of prompts, the scroll-count threshold invariant, timestamp filtering behavior, and duplicate-scheduling semantics. Add inline comments only at non-obvious state transitions, especially when deciding whether to consume signals before or after scheduling. Structured logs must use safe metadata only: user ID, iteration ID, signal counts, source name, reason code, scheduling result, and task ID. Do not log raw user text, prompts, model output, or raw behavior contexts.

Modify `backend/services/compeer_scheduler.py` first. Add proposed helper functions near the proactive scheduler logic:

- Proposed `_parse_behavior_signal_timestamp(signal: dict[str, Any]) -> float | None`.
- Proposed `_collect_recent_scroll_behavior_signals(signals: list[dict[str, Any]], *, now: float, window_seconds: float) -> list[dict[str, Any]]`.
- Proposed `_consume_behavior_signals(store: Any, user_id: str, consumed_signals: list[dict[str, Any]]) -> None`, or an equivalent method in `MemoryStore` if the existing store API needs atomic Redis updates.

If behavior-signal consumption requires atomicity, modify `backend/memory_store.py` instead of mutating Redis directly in the scheduler. Prefer a store-owned method such as proposed `consume_behavior_signals(user_id: str, consumed: list[dict[str, Any]]) -> int` because `MemoryStore` owns the Redis key format.

Update `_process_proactive_user()` in `backend/services/compeer_scheduler.py`:

1. Keep avatar summon and explicit `trigger_proactive` paths unchanged.
2. After inactivity and cooldown checks pass, call `store.get_behavior_signals(user_id)`.
3. Count recent scroll signals from `behavior_signals`.
4. Pass `scroll_count=len(recent_scroll_signals)` into `evaluate_proactive_preflight()`.
5. Block with the existing insufficient-evidence path when the count is below six.
6. Run the existing `detect_proactive_event_via_llm()` and `importance_passed` logic only after enough recent scroll signals exist.
7. Consume or mark the used scroll signals only after scheduling succeeds, or document and test any intentional earlier consumption behavior.
8. Keep the legacy hot-memory `obs_*` path only if required for backward compatibility; if retained, label it as a fallback source and keep it secondary to `behavior_signals`.

#### Expected File Tree After Phase 1

```text
backend/
├── memory_store.py                         [modified if store-owned consumption is added]
└── services/
    └── compeer_scheduler.py                [modified]
tests/
└── backend/
    └── test_compeer_scheduler.py           [modified]
```

The tree is cumulative for this phase only.

#### Work List

1. [x] Modify `backend/services/compeer_scheduler.py`.
   - [x] Add proposed `_parse_behavior_signal_timestamp()` to safely parse ISO timestamps and reject invalid timestamps without raising scheduler-level exceptions.
   - [x] Add proposed `_collect_recent_scroll_behavior_signals()` to filter `type == "scroll"` signals inside the configured behavior evidence window.
   - [x] Update `_process_proactive_user()` to call `store.get_behavior_signals(user_id)` after inactivity and cooldown checks.
   - [x] Replace the primary `hot_mem.items()` `obs_*` scroll count with behavior-signal scroll count.
   - [x] Preserve explicit `trigger_proactive` and avatar summon scheduling behavior.
   - [x] Keep or remove the legacy `obs_*` fallback intentionally; if kept, label the source as `legacy_hot_memory` in preflight metadata.
2. [x] Modify `backend/memory_store.py` only if scheduler-side consumption would be non-atomic.
   - [x] Add proposed `consume_behavior_signals(user_id, consumed_signals)` to remove or mark consumed entries from `areqa:behavior_signals:{user_id}`.
   - [x] Preserve existing `get_behavior_signals()` and `append_behavior_signal()` behavior.
3. [x] Extend `tests/backend/test_compeer_scheduler.py`.
   - [x] Add a fake store with `get_behavior_signals()` returning six recent scroll signals.
   - [x] Assert `_process_proactive_user()` schedules through the behavior-signal path when inactivity and importance gates pass.
   - [x] Assert fewer than six scroll signals block scheduling.
   - [x] Assert malformed timestamps do not crash the scheduler and do not count as valid recent scroll evidence.
   - [x] Assert explicit trigger and avatar summon tests still pass unchanged.

#### Test Plan

Add unit-level scheduler tests in `tests/backend/test_compeer_scheduler.py`. Use monkeypatches for `get_last_interaction_time()`, `is_in_cooldown()`, `detect_proactive_event_via_llm()`, `get_hot_memory_snapshot()`, and `schedule_areqa_care_letter()` so the tests stay deterministic. Assertions must cover:

- Success: six recent scroll behavior signals lead to one schedule call when the LLM event detector and importance gate pass.
- Boundary: five recent scroll signals block scheduling.
- Boundary: old scroll signals outside the selected time window do not count.
- Failure: malformed behavior signal timestamps do not crash the scheduler.
- Compatibility: explicit trigger and avatar summon behavior remain unchanged.

Command:

```bash
pytest tests/backend/test_compeer_scheduler.py -q
```

#### Expected Output / Result

When the frontend writes scroll telemetry to `behavior_signals`, the proactive scheduler can count those same scroll signals. A user who is inactive long enough, not in cooldown, and has enough recent scroll evidence can reach the existing LLM proactive-event detector and importance gate. If accepted, exactly one ComPeer mailbox task is scheduled. The Act 09 symptom `scroll_count=0` should no longer occur when recent scroll behavior signals exist.

#### Testing Script

##### Act 01: Behavior Signals Become Scheduler Evidence

Create six recent `scroll` behavior signals for one user, set last interaction time older than the inactivity threshold, disable cooldown, and make the proactive-event detector return an eligible event.

Pass condition: one ComPeer schedule call is made for that user.

##### Act 02: Insufficient Scroll Evidence Blocks Scheduling

Create five recent `scroll` behavior signals for one user and run the scheduler under the same inactivity setup.

Pass condition: no schedule call is made and the preflight reason remains an insufficient-evidence reason.

##### Act 03: Legacy Prompt Memory Is Not Required

Run the successful behavior-signal scenario with no `obs_*` keys in hot memory.

Pass condition: scheduling still succeeds.

#### Gate to Enter the Next Phase

Run:

```bash
pytest tests/backend/test_compeer_scheduler.py -q
git diff --check
```

Success requires all scheduler tests to pass, no whitespace errors, and no regression in existing explicit-trigger or avatar-summon scheduler behavior. Retain the pytest output in the worklog or implementation notes. If this gate fails, stop and fix Phase 1 before changing observability or test-script files.

#### Phase Commit

Create this commit only after the Phase 1 gate passes.

Commit message:

```text
fix(compeer): consume behavior signals for proactive scheduling
```

Stage only Phase 1 files or exact hunks:

```bash
git status --short
git add -p backend/services/compeer_scheduler.py
git add -p backend/memory_store.py
git add -p tests/backend/test_compeer_scheduler.py
git diff --cached --check
git diff --cached --stat
git commit -m "fix(compeer): consume behavior signals for proactive scheduling"
git show --stat --oneline --summary HEAD
```

If `backend/memory_store.py` is not changed in this phase, do not stage it. Preserve unrelated user changes.

### Phase 2: Add Terminal ComPeer Observability and Timing Contract

#### Problem

The Act 09 logs showed why scheduling was blocked, but they did not show the complete upstream and downstream lifecycle: behavior-signal count, signal source, trigger creation, trigger consumption, task scheduling, mailbox persistence, notification state, and duplicate suppression. The report also identified a timing mismatch: if fallback scheduling occurs near `T0 + 120` and `compeer_delivery_delay_seconds=120`, a mailbox message should normally appear closer to `T0 + 240`, not `T0 + 150`.

#### Assumptions

- The existing logging style uses Python `logging.getLogger(__name__)` with stable event-name strings such as `compeer.proactive_preflight` and `mailbox.scheduled`.
- Logs are operational evidence and must not contain raw prompts, user message text, model output, or raw behavior signal context.
- `compeer_delivery_delay_seconds` remains the source of truth for delayed mailbox visibility.
- The product may later choose a shorter test-only delay, but production code should not silently override the configured delay.

#### Solution

Extend the existing ComPeer preflight logging to include safe behavior-signal metadata and source. Add terminal lifecycle logs at the transition points that matter for Act 09: behavior evidence evaluated, proactive event accepted or rejected, schedule requested, schedule succeeded or failed, and behavior signals consumed or retained. Also document and test the delivery-delay contract so manual expectations are aligned with runtime configuration.

#### Implementation

> Context: Update Google-style docstrings for any changed preflight dataclass, helper, or public scheduler function. Document log event names, safe metadata fields, reason-code stability, and the timing contract between inactivity threshold and mailbox delivery delay. Inline comments should explain only non-obvious lifecycle boundaries, such as why a log is emitted before scheduling versus after durable task creation. Do not log raw user text, prompts, model output, raw behavior signal contexts, or credentials.

Modify `backend/services/compeer_scheduler.py`:

- Extend `ProactivePreflightResult` if necessary with safe fields such as proposed `signal_source`, `behavior_signal_count`, `recent_scroll_count`, `legacy_scroll_count`, and `delivery_delay_seconds`.
- Update `evaluate_proactive_preflight()` to accept the new safe metadata without changing its core decision semantics.
- Update `_log_proactive_preflight()` to emit stable key-value fields for signal source, scroll count, delivery delay, scheduling result, task ID, and reason.
- Add safe logs around behavior-derived scheduling:
  - `compeer.behavior_signals_evaluated`
  - `compeer.behavior_trigger_eligible`
  - `compeer.behavior_trigger_rejected`
  - `compeer.behavior_signals_consumed`
- Keep `mailbox.scheduled` in `backend/mailbox_store.py` as the durable scheduling evidence. Modify it only if required to include safe correlation metadata already available at the call site.

Modify `backend/config.py` only if a test-specific configuration value is needed. Do not change the production default of `compeer_delivery_delay_seconds=120` unless the product explicitly decides to change the user-facing behavior.

#### Expected File Tree After Phase 2

```text
backend/
├── config.py                              [modified only if test-specific config is added]
├── mailbox_store.py                       [modified only if safe correlation metadata is needed]
└── services/
    └── compeer_scheduler.py               [modified]
tests/
└── backend/
    ├── test_compeer_scheduler.py          [modified]
    └── test_config.py                     [modified only if config changes]
```

The tree is cumulative from Phase 1.

#### Work List

1. [x] Modify `backend/services/compeer_scheduler.py`.
   - [x] Extend `ProactivePreflightResult` with safe behavior-signal and timing metadata if needed.
   - [x] Update `evaluate_proactive_preflight()` to preserve existing reason-code behavior while carrying metadata.
   - [x] Update `_log_proactive_preflight()` to log source, counts, delivery delay, scheduling result, and task ID.
   - [x] Add lifecycle logs in `_process_proactive_user()` for behavior-signal evaluation, eligibility, rejection, scheduling, and consumption.
2. [x] Modify `backend/mailbox_store.py` only if required.
   - [x] Keep or extend `mailbox.scheduled` so it remains the durable evidence that a delayed mailbox task exists. No code change was required.
   - [x] Avoid raw message body logging. Existing mailbox scheduling logs already avoid raw message body logging.
3. [x] Modify `backend/config.py` only if required.
   - [x] Preserve the production `compeer_delivery_delay_seconds=120` default. No code change was required.
   - [x] Add any test override through existing settings patterns if the tests need deterministic shorter delivery. No override was required for Phase 2 tests.
4. [x] Extend `tests/backend/test_compeer_scheduler.py`.
   - [x] Assert behavior-signal lifecycle logs include safe event names and reason codes.
   - [x] Assert no raw behavior context or message text is emitted in scheduler logs.
   - [x] Assert delivery-delay metadata matches configured settings.
5. [x] Extend `tests/backend/test_config.py` only if config changes.
   - [x] Assert the default `compeer_delivery_delay_seconds` remains 120. Existing config tests passed; no config hunk was needed.
   - [x] Assert any test override parses correctly. Not applicable because no new override was added.

#### Test Plan

Use `caplog` in `tests/backend/test_compeer_scheduler.py` to validate event names and safe metadata. Keep tests focused on structured event content, not full free-form log sentences. If `backend/config.py` changes, update `tests/backend/test_config.py`.

Commands:

```bash
pytest tests/backend/test_compeer_scheduler.py tests/backend/test_config.py -q
```

#### Expected Output / Result

For a behavior-derived ComPeer attempt, logs should show:

- How many recent behavior signals were evaluated.
- Which source was used, for example `behavior_signals`.
- Whether the preflight was eligible or blocked.
- Whether scheduling succeeded.
- The configured delivery delay.
- Whether behavior signals were consumed after successful scheduling.

Operators should be able to distinguish these cases without reading code: no telemetry received, insufficient scroll evidence, trigger rejected by LLM, failed importance gate, schedule failed, delayed mailbox task created, and mailbox worker delivery pending.

#### Testing Script

##### Act 01: Observe Eligible Behavior Path

Run the scheduler with six recent scroll behavior signals and eligible proactive-event detector output.

Pass condition: logs include behavior-signal source, recent scroll count, delivery delay, and scheduling success.

##### Act 02: Observe Blocked Behavior Path

Run the scheduler with no behavior signals.

Pass condition: logs show zero behavior signals and a safe block reason without raw user data.

##### Act 03: Confirm Delivery Delay Contract

Inspect settings used by scheduling.

Pass condition: scheduler logs or tests prove delayed delivery uses `compeer_delivery_delay_seconds`.

#### Gate to Enter the Next Phase

Run:

```bash
pytest tests/backend/test_compeer_scheduler.py tests/backend/test_config.py -q
git diff --check
```

Success requires all tests to pass, safe log assertions to pass, and no production default timing change unless explicitly documented. If this gate fails, stop and fix observability before changing manual test documents.

#### Phase Commit

Create this commit only after the Phase 2 gate passes.

Commit message:

```text
chore(compeer): add proactive scheduling observability
```

Stage only Phase 2 files or exact hunks:

```bash
git status --short
git add -p backend/services/compeer_scheduler.py
git add -p backend/mailbox_store.py
git add -p backend/config.py
git add -p tests/backend/test_compeer_scheduler.py
git add -p tests/backend/test_config.py
git diff --cached --check
git diff --cached --stat
git commit -m "chore(compeer): add proactive scheduling observability"
git show --stat --oneline --summary HEAD
```

Skip files that were not changed. Preserve unrelated user changes.

### Phase 3: Add End-to-End Regression Coverage and Update Manual Validation Contract

#### Problem

The current tests cover explicit ComPeer trigger behavior and mailbox flow, but they do not protect the full path that failed in Act 09: frontend or API scroll telemetry, behavior-signal persistence, scheduler fallback, delayed mailbox scheduling, mailbox delivery, and UI-visible mailbox state. The manual script also uses `T0 + 150` as a hard mailbox-delivery deadline, which conflicts with a fallback schedule created after the inactivity threshold plus a 120-second delivery delay.

#### Assumptions

- Backend integration tests can simulate `/api/v1/log_action` without a real browser.
- Existing mailbox tests already provide patterns for delayed mailbox persistence and worker delivery.
- Frontend tests should verify that `ProactiveManager` sends scroll telemetry, but backend tests should own scheduling correctness.
- The manual test script should remain human-executable and should not require strict database inspection for every act.

#### Solution

Add a focused backend integration test that covers the API-to-scheduler behavior-signal path. Reuse existing mailbox-store test patterns to verify one durable ComPeer mailbox task or delivered mailbox record. Keep frontend coverage narrow: verify scroll telemetry is sent, not that frontend controls backend scheduling. Update the manual test script to clarify when `T0` starts and how `compeer_delivery_delay_seconds` affects the expected mailbox window.

#### Implementation

> Context: Add Google-style docstrings to any new test helper or fixture that encodes non-obvious scheduler timing, fake Redis behavior, or mailbox delivery semantics. Document the ownership boundary: frontend emits telemetry, memory gate persists behavior signals, scheduler evaluates behavior signals, mailbox store owns delayed delivery, and UI only displays mailbox state. Inline comments should explain test time control and duplicate-suppression assertions. Logs asserted in tests must use safe metadata and stable event names only.

Modify or add backend integration tests:

- Prefer extending `tests/backend/test_compeer_integration.py` if it already owns `/api/v1/log_action` plus ComPeer behavior.
- Otherwise add proposed `tests/backend/test_compeer_behavior_signal_flow.py`.
- Simulate six `/api/v1/log_action` scroll calls for the authenticated test user.
- Assert Redis or fake store contains `areqa:behavior_signals:{user_id}` entries.
- Run or directly invoke the scheduler under controlled inactivity and cooldown state.
- Assert exactly one ComPeer delayed mailbox task or mailbox record is created.
- Assert duplicate scheduler runs do not create duplicate messages from the same consumed signal batch.

Modify `tests/frontend/ProactiveManager.test.tsx` only if existing coverage does not already prove scroll telemetry is sent to `/api/v1/log_action`.

Modify `docs/worklog/202607/2026_07_18_experiment/test_script_2026_07_18_check.md` only if the implementation decision changes the manual timing contract. Keep it as a manual user simulation script, not a strict backend test script.

#### Expected File Tree After Phase 3

```text
docs/
└── worklog/
    └── 202607/
        └── 2026_07_18_experiment/
            └── test_script_2026_07_18_check.md       [modified if timing contract changes]
tests/
├── backend/
│   ├── test_compeer_integration.py                    [modified if reused]
│   └── test_compeer_behavior_signal_flow.py           [new if a new file is clearer]
└── frontend/
    └── ProactiveManager.test.tsx                      [modified only if coverage is missing]
```

The tree is cumulative from Phases 1 and 2.

#### Work List

1. [ ] Modify `tests/backend/test_compeer_integration.py` or create proposed `tests/backend/test_compeer_behavior_signal_flow.py`.
   - [ ] Add a test that posts six scroll actions through `/api/v1/log_action`.
   - [ ] Assert the actions are persisted through `append_behavior_signal()` or the fake Redis behavior-signal key.
   - [ ] Invoke `_process_proactive_user()` or the scheduler loop with deterministic inactivity and cooldown state.
   - [ ] Assert one ComPeer task or mailbox record is created.
   - [ ] Run the scheduler again and assert no duplicate task or mailbox record is created from the same consumed signals.
2. [ ] Modify `tests/frontend/ProactiveManager.test.tsx` only if needed.
   - [ ] Assert scroll actions are throttled and sent to `/api/v1/log_action` with safe telemetry context.
   - [ ] Avoid asserting backend scheduling behavior in frontend tests.
3. [ ] Modify `docs/worklog/202607/2026_07_18_experiment/test_script_2026_07_18_check.md` if timing contract changes.
   - [ ] Clarify whether `T0` means the time of last user interaction, scheduler eligibility, or task scheduling.
   - [ ] If production delay remains 120 seconds, update Act 09 to wait for inactivity threshold plus delivery delay, or instruct the tester to use a test environment with a shortened delay.
   - [ ] Keep Act 09's user-facing pass condition: exactly one mailbox message, no direct chat interruption, unread UI synchronized, and safe content boundaries.

#### Test Plan

Run focused backend and frontend tests:

```bash
pytest tests/backend/test_compeer_scheduler.py tests/backend/test_compeer_integration.py tests/backend/test_mailbox_flow.py -q
npm --prefix frontend test -- ProactiveManager.test.tsx
```

If a new backend test file is created, include it explicitly:

```bash
pytest tests/backend/test_compeer_behavior_signal_flow.py -q
```

Assertions must cover the full regression path: API telemetry write, behavior-signal storage, scheduler read, schedule creation, duplicate suppression, and mailbox visibility after delayed delivery when the worker path is exercised.

#### Expected Output / Result

The automated regression suite should fail if `/api/v1/log_action` writes scroll telemetry to a path that the scheduler does not read. The manual Act 09 script should match the actual timing contract and should allow a human tester to reproduce ComPeer mailbox delivery without guessing whether `T0 + 150` is measured from last interaction or from task scheduling.

#### Testing Script

##### Act 01: API-to-Scheduler Regression

Submit six scroll events through `/api/v1/log_action`, advance inactivity, and run the ComPeer scheduler.

Pass condition: one ComPeer schedule or mailbox record exists for the authenticated user.

##### Act 02: Duplicate Suppression

Run the scheduler again without adding new scroll behavior signals.

Pass condition: no second ComPeer task or mailbox record is created.

##### Act 03: Manual Act 09 Timing

Follow the updated manual Act 09 timing instructions in the worklog test script.

Pass condition: exactly one ComPeer mailbox message appears within the documented timing window.

#### Gate to Enter the Next Phase

This is the final implementation phase. Run:

```bash
pytest tests/backend/test_compeer_scheduler.py tests/backend/test_compeer_integration.py tests/backend/test_mailbox_flow.py -q
pytest tests/backend/test_compeer_behavior_signal_flow.py -q
npm --prefix frontend test -- ProactiveManager.test.tsx
git diff --check
```

If `tests/backend/test_compeer_behavior_signal_flow.py` was not created, omit that command and document why existing integration coverage is sufficient. Success requires all focused tests to pass, the manual script to match the implementation timing contract, and no whitespace errors. If any test fails, fix Phase 3 before committing.

#### Phase Commit

Create this commit only after the Phase 3 gate passes.

Commit message:

```text
test(compeer): cover behavior-signal mailbox flow
```

Stage only Phase 3 files or exact hunks:

```bash
git status --short
git add -p tests/backend/test_compeer_integration.py
git add -p tests/backend/test_compeer_behavior_signal_flow.py
git add -p tests/backend/test_mailbox_flow.py
git add -p tests/frontend/ProactiveManager.test.tsx
git add -p docs/worklog/202607/2026_07_18_experiment/test_script_2026_07_18_check.md
git diff --cached --check
git diff --cached --stat
git commit -m "test(compeer): cover behavior-signal mailbox flow"
git show --stat --oneline --summary HEAD
```

Skip files that were not changed. Preserve unrelated user changes.

### Cross-Phase Regression and Final Acceptance

After all phase commits exist, run the focused backend and frontend regression suite:

```bash
pytest tests/backend/test_compeer_scheduler.py tests/backend/test_compeer_integration.py tests/backend/test_mailbox_flow.py tests/backend/test_config.py -q
pytest tests/backend/test_compeer_behavior_signal_flow.py -q
npm --prefix frontend test -- ProactiveManager.test.tsx
git status --short
git log --oneline -3
```

If the repository has a broader backend or frontend check command documented elsewhere, run it after the focused suite and record the command plus result in the worklog. Do not replace the focused suite with a broad build command; the focused suite is required because it protects the exact Act 09 regression path.

Final acceptance requires:

- `/api/v1/log_action` scroll telemetry remains stored as `behavior_signals`.
- ComPeer scheduler reads recent scroll evidence from `behavior_signals`.
- Legacy `hot_memory` `obs_*` entries are no longer required for behavior-derived ComPeer scheduling.
- A user with enough recent scroll evidence, sufficient inactivity, no cooldown, and accepted proactive-event/importance gates schedules exactly one ComPeer mailbox task.
- Re-running the scheduler without new evidence does not duplicate the message.
- Logs expose safe lifecycle evidence for signal evaluation, preflight block or eligibility, scheduling result, and delivery delay.
- The manual Act 09 script's timing window matches the configured delivery behavior.
- `git status --short` shows no planned implementation changes left uncommitted.
- `git log --oneline` shows the ordered phase commits:
  1. `fix(compeer): consume behavior signals for proactive scheduling`
  2. `chore(compeer): add proactive scheduling observability`
  3. `test(compeer): cover behavior-signal mailbox flow`

Remaining risks:

- The proactive-event LLM detector may still reject normal scroll behavior even after the scheduler can see behavior signals. Mitigation: keep the success test deterministic by monkeypatching detector output, and add a separate product decision if normal scrolling alone should always or only sometimes trigger ComPeer.
- Mailbox delivery timing may still feel slow in manual tests because production delay is 120 seconds. Mitigation: document the timing contract and use a test-specific delay only through explicit configuration.
- Existing scheduler logs use key-value formatted log strings rather than a dedicated structured logging library. Mitigation: keep stable event names and safe metadata fields so tests can assert lifecycle evidence without depending on raw free-form prose.
