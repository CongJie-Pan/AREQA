# Backend Main and Services Restructure Plan

This plan extends the previous backend split by addressing two remaining structural problems: `backend/main.py` is still a 1,677-line FastAPI composition module, and `backend/services/` still mixes unrelated domains in one flat directory. The phase order first extracts route and bootstrap ownership from `main.py` while preserving API/SSE behavior, then consolidates flat services into domain folders with compatibility facades so existing imports and tests continue to work at every commit.

Confirmed current line-count pressure points:

```text
1677 backend/main.py
1487 backend/services/compeer_scheduler.py
 652 backend/services/conversation_context_service.py
 639 backend/services/conversation_stream_service.py
 617 backend/services/parts_context_service.py
 599 backend/services/paper_visual_planner_service.py
 585 backend/services/visual_answer_service.py
 566 backend/services/memory_ingestion_service.py
 539 backend/services/visual_grounding_agent.py
```

Target line ceiling: keep every modified production Python file at or below 657 lines unless a phase explicitly documents a temporary exception and resolves it before final acceptance.

### Phase 1: Extract Application Bootstrap and Runtime State

#### Problem

`backend/main.py` owns environment loading, logging setup, model constants, global service construction, thread pool setup, RAG cache state, and the FastAPI app object. This makes route extraction risky because endpoints currently close over global symbols from the same file. The target state is a small `main.py` facade that imports an app assembled by dedicated bootstrap modules while preserving `backend.main.app`, global patch points used by tests, and startup/shutdown behavior.

#### Assumptions

`backend.main.app`, `rag_service`, `router_service`, `suggestion_service`, `rag_cache`, `_thread_pool`, `HF_TOKEN`, `HF_ENDPOINT_URL`, `HF_REPO_ID`, and `PROJECT_ROOT` are compatibility boundaries because tests and runtime modules patch or import them. If this assumption is false, the implementer must inspect all callers with `rg "backend\\.main|from main import|import main"` and expand the compatibility facade before committing.

#### Solution

Create `backend/app/` as the application composition package. Move configuration loading, logging setup, runtime feature schema, prompt constants, shared thread pool, and service registry helpers into focused modules. Keep `backend/main.py` as the public facade that initializes and exports the same app and compatibility globals.

#### Implementation

> Context: Add Google-style docstrings for every new public module, class, and function. Document why `backend/main.py` remains a compatibility facade, which globals are intentionally re-exported, and which structured logs are safe. Use inline comments only for compatibility or lifecycle-order reasons, not for obvious assignments.

Add `backend/app/bootstrap.py` with `load_environment()`, `configure_logging()`, and `create_app()`. Add `backend/app/runtime_state.py` with `RuntimeState`, `get_query_fingerprint()`, `_env_flag()`, and `init_rag_service()`. Add `backend/app/prompts.py` for `BASE_PERSONA`, `RESPONSE_POLICY_OVERLAYS`, `SYSTEM_PROMPT_NORMAL`, `SYSTEM_PROMPT_FORCE_THINK`, `SYSTEM_PROMPT_WITH_RAG`, and `SYSTEM_PROMPT_WITH_RAG_THINK`. Update `backend/main.py` to import and re-export these symbols without changing external values.

#### Expected File Tree After Phase 1

```text
backend/
├── main.py                              [modified]
└── app/
    ├── __init__.py                      [new]
    ├── bootstrap.py                     [new]
    ├── prompts.py                       [new]
    └── runtime_state.py                 [new]
```

#### Work List

1. [ ] Create `backend/app/bootstrap.py`.
   - [ ] Add proposed `configure_logging()` and move logging setup from `backend/main.py`.
   - [ ] Add proposed `load_environment(project_root: Path)` and move `.env` loading.
   - [ ] Add proposed `create_app()` and construct `FastAPI(title="XiaoHong Ancient Chinese QA - RAG Backend API")`.
2. [ ] Create `backend/app/runtime_state.py`.
   - [ ] Add proposed `RuntimeState` for `rag_cache`, `rag_service`, `_thread_pool`, and resolved model name.
   - [ ] Move `get_query_fingerprint()` and `_env_flag()` from `backend/main.py`.
   - [ ] Move `init_rag_service()` while preserving missing-index and disabled-RAG behavior.
3. [ ] Create `backend/app/prompts.py`.
   - [ ] Move system prompt constants and `RuntimeFeatureResponse`.
4. [ ] Modify `backend/main.py`.
   - [ ] Re-export `app`, `rag_cache`, `rag_service`, `_thread_pool`, `get_query_fingerprint()`, `init_rag_service()`, prompt constants, and runtime feature schema.
   - [ ] Keep existing test patch paths working.

#### Test Plan

Run import and startup-focused tests: `tests/backend/test_stream_endpoint.py`, `tests/backend/test_stream_api_perplexity.py`, `tests/backend/test_rag_service.py`, `tests/backend/test_orchestration_service.py`, and `tests/unit/test_orchestration_service.py`. Assert `backend.main.app` still exists, `/api/v1/features` returns the same shape, internal RAG remains disabled unless `ENABLE_INTERNAL_RAG=true`, and `get_query_fingerprint()` returns stable values.

#### Expected Output / Result

`backend/main.py` no longer owns raw bootstrap implementation but exports the same public symbols. FastAPI app creation, logging, environment loading, prompt constants, RAG initialization, and cache fingerprint behavior remain unchanged.

#### Testing Script

##### Act 01: Import Main Facade

Import `backend.main` in a clean Python process.

Pass condition: `backend.main.app`, `backend.main.get_query_fingerprint`, and `backend.main.init_rag_service` exist without import errors.

##### Act 02: Runtime Feature Endpoint

Call `GET /api/v1/features` through `httpx.AsyncClient` and the ASGI app.

Pass condition: response is HTTP 200 and contains `mailbox`, `compeer`, and `compeerTelemetry`.

##### Act 03: RAG Disabled Default

Unset `ENABLE_INTERNAL_RAG` and call `backend.main.init_rag_service()`.

Pass condition: it returns `None` and does not raise.

#### Gate to Enter the Next Phase

Run:

```bash
python -m py_compile backend/main.py backend/app/*.py
./backend/.venv/bin/python -m pytest tests/unit/test_orchestration_service.py tests/backend/test_stream_endpoint.py tests/backend/test_stream_api_perplexity.py tests/backend/test_rag_service.py tests/backend/test_orchestration_service.py -q
wc -l backend/main.py backend/app/*.py
```

Every command must pass, `backend/main.py` must be below 1,200 lines after this phase, and no public import or endpoint behavior may change. If a test fails because a patch point moved, restore the patch point through the facade before proceeding.

#### Phase Commit

Commit message:

```text
refactor(app): extract backend bootstrap and runtime state
```

Stage only `backend/main.py` and `backend/app/`. Run `git status --short`, `git diff --cached --check`, `git diff --cached --stat`, commit once, then verify with `git show --stat --oneline --summary HEAD`.

### Phase 2: Move Memory and Mailbox Routes Out of Main

#### Problem

`backend/main.py` contains memory view construction, explicit memory editing helpers, candidate confirmation/rejection endpoints, memory flush/delete endpoints, mailbox feature checks, send/read endpoints, and mailbox task id generation. These route families are independent of stream request handling but currently enlarge `main.py` and force unrelated imports into the app entry point.

#### Assumptions

Routes under `/api/v1/memory*` and `/api/v1/mailbox*` must keep exact paths, request/response shapes, authentication dependencies, status codes, and side effects. Helper functions such as `build_memory_view()` may be imported or tested through `backend.main`, so the facade should re-export them during this refactor.

#### Solution

Create route modules under `backend/app/routes/` and service helpers under domain folders where needed. Register routers from bootstrap or `main.py`. Keep endpoint names stable where tests reference them.

#### Implementation

> Context: Add Google-style docstrings for new route modules and public helpers. Document authentication boundaries, mailbox feature gating, memory-source provenance, and fail-soft behavior. Structured logs must use safe user IDs/correlation IDs and reason codes only; do not log raw memory text or mail content.

Add `backend/app/routes/memory.py` for memory endpoints and explicit memory editing helpers. Add `backend/app/routes/mailbox.py` for mailbox endpoints and feature gating. If helper logic grows, add `backend/services/memory/routes.py` or `backend/services/mailbox/commands.py`; otherwise keep route-local private helpers.

#### Expected File Tree After Phase 2

```text
backend/
├── main.py                              [modified]
└── app/
    └── routes/
        ├── __init__.py                  [new]
        ├── memory.py                    [new]
        └── mailbox.py                   [new]
```

#### Work List

1. [ ] Create `backend/app/routes/__init__.py`.
   - [ ] Add proposed `register_routes(app: FastAPI)` or export route modules for bootstrap registration.
2. [ ] Create `backend/app/routes/memory.py`.
   - [ ] Move `fetch_memory()`, `get_memory_summary()`, `memory_debug_endpoint()`, `confirm_candidate_memory_endpoint()`, `reject_candidate_memory_endpoint()`, `clear_working_memory_endpoint()`, `flush_memory_endpoint()`, `delete_memory_endpoint()`, `batch_delete_memory_endpoint()`, `edit_memory_endpoint()`, and `clear_memory_endpoint()`.
   - [ ] Move `_memory_source_id()`, `build_memory_view()`, `_find_profile_memory()`, `_find_candidate_memory()`, `_delete_explicit_profile_memory()`, `_update_explicit_profile_memory()`, and `_get_candidate_by_memory_id()`.
   - [ ] Move request schemas `EditMemoryRequest` and `DeleteBatchRequest`.
3. [ ] Create `backend/app/routes/mailbox.py`.
   - [ ] Move `_ensure_mailbox_feature_enabled()`, `fetch_mailbox()`, `SendMailRequest`, `_mailbox_reply_task_id()`, `send_mail_endpoint()`, and `read_mail_endpoint()`.
4. [ ] Modify `backend/main.py`.
   - [ ] Register the memory and mailbox routers.
   - [ ] Re-export compatibility helpers and request models used by tests.

#### Test Plan

Run `tests/backend/test_memory_store.py`, `tests/backend/test_memory_store_compeer.py`, `tests/backend/test_memory_source_boundaries.py`, `tests/backend/test_compeer_behavior_signal_flow.py`, `tests/backend/test_stream_endpoint.py`, and any mailbox route tests discovered by `rg "mailbox" tests`. Add route-level regression tests if existing coverage does not assert status codes and auth behavior.

#### Expected Output / Result

All memory and mailbox endpoints continue to respond under the same paths. `main.py` line count drops substantially, while memory/mailbox behavior is owned by route modules with explicit auth and feature boundaries.

#### Testing Script

##### Act 01: Memory Summary Route

Call `GET /api/v1/memory/summary` with an authenticated user fixture.

Pass condition: response schema matches the previous summary response.

##### Act 02: Candidate Confirm Route

Patch the memory store with a candidate and call `POST /api/v1/memory/candidates/{memory_id}/confirm`.

Pass condition: candidate is confirmed once and the response status remains unchanged.

##### Act 03: Mailbox Disabled Gate

Disable mailbox features and call `GET /api/v1/mailbox`.

Pass condition: endpoint returns the same disabled status code and error shape as before.

#### Gate to Enter the Next Phase

Run:

```bash
python -m py_compile backend/main.py backend/app/routes/*.py
./backend/.venv/bin/python -m pytest tests/backend/test_memory_store.py tests/backend/test_memory_store_compeer.py tests/backend/test_memory_source_boundaries.py tests/backend/test_compeer_behavior_signal_flow.py tests/backend/test_stream_endpoint.py -q
wc -l backend/main.py backend/app/routes/*.py
```

All commands must pass. `backend/main.py` must be below 1,000 lines after this phase. Restore facade re-exports for any failing legacy imports before continuing.

#### Phase Commit

Commit message:

```text
refactor(api): extract memory and mailbox routes
```

Stage only `backend/main.py`, `backend/app/routes/__init__.py`, `backend/app/routes/memory.py`, and `backend/app/routes/mailbox.py`. Run staged diff checks and commit exactly this phase.

### Phase 3: Move Stream, Attachment, WebSocket, and Utility Routes

#### Problem

`backend/main.py` still owns request parsing for `/api/v1/stream`, attachment validation handoff, SSE terminal wrapping, WebSocket notification tickets, retrieve/debug/log endpoints, and title generation. These are operationally distinct API surfaces but share app-level clients and service registry state.

#### Assumptions

`/api/v1/stream` is the highest-risk route because it exposes SSE ordering, terminal `[DONE]`, attachment payload handling, and orchestrator construction. Tests patch `backend.main.AsyncOpenAI`, `backend.main.rag_service`, `backend.main.router_service`, and `backend.main.suggestion_service`, so the route module must resolve those through a compatibility provider rather than freezing stale references at import time.

#### Solution

Create dedicated route modules for streaming, titles, retrieval, diagnostics/logging, and notifications. Add `backend/app/dependencies.py` to provide current clients/services from runtime state and preserve patchability.

#### Implementation

> Context: Add Google-style docstrings documenting SSE terminal guarantees, attachment size limits, auth boundaries, and WebSocket ticket validation. Inline comments should explain only lifecycle and compatibility decisions. Structured logs must keep event names stable and must not include raw user messages, prompts, attachments, tokens, or credentials.

Add `backend/app/dependencies.py` with proposed `get_runtime_services()` and `create_openai_client()` helpers. Move stream request parsing and `stream_endpoint()` to `backend/app/routes/stream.py`. Move title helpers and endpoint to `backend/app/routes/title.py`. Move retrieve/debug/log/proactive-check endpoints to `backend/app/routes/diagnostics.py`. Move WebSocket ticket and notification endpoint to `backend/app/routes/notifications.py`.

#### Expected File Tree After Phase 3

```text
backend/
├── main.py                              [modified]
└── app/
    ├── dependencies.py                  [new]
    └── routes/
        ├── diagnostics.py               [new]
        ├── notifications.py             [new]
        ├── stream.py                    [new]
        └── title.py                     [new]
```

#### Work List

1. [ ] Create `backend/app/dependencies.py`.
   - [ ] Add proposed `get_runtime_services()` that returns router, RAG, suggestion, cache, and thread-pool references from `backend.main` compatibility state.
   - [ ] Add proposed `create_openai_client()` that preserves `AsyncOpenAI` patch behavior.
2. [ ] Create `backend/app/routes/stream.py`.
   - [ ] Move `ChatRequest`, `_parse_bool()`, `parse_stream_request()`, and `stream_endpoint()`.
   - [ ] Preserve multipart attachment handling and SSE terminal event behavior.
3. [ ] Create `backend/app/routes/title.py`.
   - [ ] Move `TitleRequest`, `normalize_generated_title()`, `build_title_messages()`, `first_user_message_content()`, `build_title_system_prompt()`, and `generate_title_endpoint()`.
4. [ ] Create `backend/app/routes/diagnostics.py`.
   - [ ] Move `ActionLogRequest`, `ShareDebugLogRequest`, `MemoryQueryRequest`, `_safe_share_debug_context()`, `log_share_debug()`, `log_action()`, `retrieve_endpoint()`, and `proactive_check_endpoint()`.
5. [ ] Create `backend/app/routes/notifications.py`.
   - [ ] Move `generate_ws_ticket()` and `ws_notifications()`.
6. [ ] Modify `backend/main.py`.
   - [ ] Register new routers.
   - [ ] Re-export moved schemas and helpers for compatibility.

#### Test Plan

Run `tests/backend/test_stream_endpoint.py`, `tests/backend/test_stream_api_perplexity.py`, `tests/backend/test_attachment_service.py`, `tests/backend/test_orchestration_service.py`, `tests/backend/test_rag_service.py`, and title route tests discovered by `rg "generate-title|normalize_generated_title|TitleRequest" tests`. Add focused tests for multipart parsing if current tests only cover happy paths.

#### Expected Output / Result

Stream, title, retrieve, diagnostics, proactive, and notification routes behave exactly as before. `main.py` becomes primarily route registration and compatibility exports, and stream dependencies remain patchable through existing tests.

#### Testing Script

##### Act 01: Stream JSON Request

Call `POST /api/v1/stream` with a minimal JSON chat payload.

Pass condition: response is `text/event-stream`, includes `event: metadata`, and terminates with `data: [DONE]`.

##### Act 02: Stream Multipart Request

Call `POST /api/v1/stream` with a PDF attachment and text message.

Pass condition: orchestrator receives parsed `attachments` and `attachment_visual_sources` exactly once.

##### Act 03: Generate Title

Call `POST /api/v1/generate-title` with a realistic first user message and assistant answer.

Pass condition: normalized title is non-empty and follows the existing language/length constraints.

##### Act 04: Notification Ticket

Call `POST /api/v1/ws/ticket`, then connect to `/api/v1/ws/notifications`.

Pass condition: ticket is accepted once and invalid tickets are rejected as before.

#### Gate to Enter the Next Phase

Run:

```bash
python -m py_compile backend/main.py backend/app/*.py backend/app/routes/*.py
./backend/.venv/bin/python -m pytest tests/backend/test_stream_endpoint.py tests/backend/test_stream_api_perplexity.py tests/backend/test_attachment_service.py tests/backend/test_orchestration_service.py tests/backend/test_rag_service.py -q
wc -l backend/main.py backend/app/routes/*.py backend/app/*.py
```

All commands must pass. `backend/main.py` must be below 657 lines after this phase. Any SSE ordering, content type, terminal event, or attachment regression blocks the next phase.

#### Phase Commit

Commit message:

```text
refactor(api): extract stream and utility routes
```

Stage only `backend/main.py`, `backend/app/dependencies.py`, and the Phase 3 route modules. Review staged stat and diff check before committing.

### Phase 4: Split ComPeer Scheduler Into a Domain Package

#### Problem

`backend/services/compeer_scheduler.py` is 1,487 lines and combines scheduling, mailbox writes, event detection, behavior state, notification coordination, and worker lifecycle. It is the largest remaining flat service and should be moved into a domain folder before broad service reorganization.

#### Assumptions

Existing imports from `services.compeer_scheduler` must keep working. Scheduler state, task IDs, mailbox scheduling semantics, and notification behavior are compatibility boundaries. If hidden callers import private functions, the facade must temporarily re-export them until tests and callers are migrated.

#### Solution

Create `backend/services/compeer/` as the domain package. Split scheduler code by responsibility: models/state, learner event detection, mailbox scheduling, notifications, worker lifecycle, and facade. Keep `backend/services/compeer_scheduler.py` as a compatibility facade under 200 lines.

#### Implementation

> Context: Add Google-style docstrings for scheduler modules and public functions. Document idempotency keys, retry/fail-soft behavior, mailbox side effects, state ownership, and safe structured-log event names. Do not log raw learner content, generated letters, prompts, credentials, or mailbox body text.

Move durable scheduling and event helpers into `backend/services/compeer/scheduler.py`, notification publishing into `backend/services/compeer/notifications.py`, mailbox-related commands into `backend/services/compeer/mailbox.py`, state models into `backend/services/compeer/models.py`, and worker lifecycle into `backend/services/compeer/workers.py`.

#### Expected File Tree After Phase 4

```text
backend/
└── services/
    ├── compeer_scheduler.py             [modified]
    └── compeer/
        ├── __init__.py                  [new]
        ├── mailbox.py                   [new]
        ├── models.py                    [new]
        ├── notifications.py             [new]
        ├── scheduler.py                 [new]
        └── workers.py                   [new]
```

#### Work List

1. [ ] Create `backend/services/compeer/models.py`.
   - [ ] Move proposed scheduler dataclasses/enums/state constants from `backend/services/compeer_scheduler.py`.
2. [ ] Create `backend/services/compeer/mailbox.py`.
   - [ ] Move proposed mailbox scheduling and delayed-letter helpers.
3. [ ] Create `backend/services/compeer/notifications.py`.
   - [ ] Move proposed notification dispatch and WebSocket-facing coordination helpers.
4. [ ] Create `backend/services/compeer/scheduler.py`.
   - [ ] Move proposed `set_last_interaction_time()` and proactive scheduling functions.
5. [ ] Create `backend/services/compeer/workers.py`.
   - [ ] Move proposed background worker lifecycle and polling loops.
6. [ ] Modify `backend/services/compeer_scheduler.py`.
   - [ ] Re-export public scheduler API and preserve patch paths used by tests.

#### Test Plan

Run `tests/backend/test_compeer_scheduler.py`, `tests/backend/test_compeer_integration.py`, `tests/backend/test_gum_integration_compeer.py`, `tests/backend/test_compeer_behavior_signal_flow.py`, `tests/backend/test_memory_store_compeer.py`, and stream endpoint tests that patch ComPeer timestamp updates.

#### Expected Output / Result

ComPeer scheduler behavior, task IDs, mailbox scheduling, and notification dispatch remain unchanged. No file in the ComPeer package exceeds 657 lines, and the legacy facade remains import-compatible.

#### Testing Script

##### Act 01: Interaction Timestamp

Patch scheduler storage and call `set_last_interaction_time("user-a", timestamp)`.

Pass condition: timestamp is persisted or scheduled exactly as before.

##### Act 02: Proactive Event Flow

Simulate a learner state/event that should trigger a proactive letter.

Pass condition: exactly one mailbox/scheduler action is created with the same idempotency behavior.

##### Act 03: Notification Dispatch

Patch the notification manager and trigger a queued notification.

Pass condition: notification payload shape and recipient routing match the old behavior.

#### Gate to Enter the Next Phase

Run:

```bash
python -m py_compile backend/services/compeer_scheduler.py backend/services/compeer/*.py
./backend/.venv/bin/python -m pytest tests/backend/test_compeer_scheduler.py tests/backend/test_compeer_integration.py tests/backend/test_gum_integration_compeer.py tests/backend/test_compeer_behavior_signal_flow.py tests/backend/test_memory_store_compeer.py tests/backend/test_stream_endpoint.py -q
wc -l backend/services/compeer_scheduler.py backend/services/compeer/*.py
```

All commands must pass. Every modified or new file must be at or below 657 lines.

#### Phase Commit

Commit message:

```text
refactor(compeer): split scheduler domain modules
```

Stage only `backend/services/compeer_scheduler.py` and `backend/services/compeer/`. Run staged diff checks and commit exactly this phase.

### Phase 5: Consolidate Conversation Services Into a Package

#### Problem

`conversation_context_service.py`, `conversation_stream_service.py`, and `parts_context_service.py` remain flat service files and two are near or above the line ceiling. They are tightly related to prompt context assembly and stream execution but live beside unrelated services, making the services directory hard to scan.

#### Assumptions

Imports from `services.conversation_context_service`, `services.conversation_stream_service`, and `services.parts_context_service` must remain valid. SSE chunk stripping, tool-call streaming, context memory boundaries, PARTS rewrite timeouts, and response policy overlays are behavior boundaries.

#### Solution

Create `backend/services/conversation/` and move internal implementations there. Keep thin compatibility facades in the original files. Split shared conversation contracts and prompt helpers into separate modules only where they reduce real dependencies.

#### Implementation

> Context: Add Google-style docstrings describing prompt assembly boundaries, memory privacy rules, SSE terminal behavior, and PARTS timeout/fallback semantics. Require structured logs to use conversation IDs, route names, and safe reason codes only.

Move context-building internals into `backend/services/conversation/context.py`, stream execution internals into `backend/services/conversation/stream.py`, PARTS context internals into `backend/services/conversation/parts.py`, and shared models/helpers into `backend/services/conversation/models.py` if needed.

#### Expected File Tree After Phase 5

```text
backend/
└── services/
    ├── conversation_context_service.py  [modified]
    ├── conversation_stream_service.py   [modified]
    ├── parts_context_service.py         [modified]
    └── conversation/
        ├── __init__.py                  [new]
        ├── context.py                   [new]
        ├── models.py                    [new]
        ├── parts.py                     [new]
        └── stream.py                    [new]
```

#### Work List

1. [ ] Create `backend/services/conversation/context.py`.
   - [ ] Move proposed `ConversationContextService` implementation internals.
2. [ ] Create `backend/services/conversation/stream.py`.
   - [ ] Move proposed `ConversationStreamService` implementation internals.
3. [ ] Create `backend/services/conversation/parts.py`.
   - [ ] Move proposed `PartsContextService` implementation internals.
4. [ ] Create `backend/services/conversation/models.py`.
   - [ ] Move shared dataclasses/contracts only if used by two or more conversation modules.
5. [ ] Modify legacy facade files.
   - [ ] Re-export `ConversationContextService`, `ConversationStreamService`, and `PartsContextService`.

#### Test Plan

Run `tests/backend/test_conversation_context_service.py`, `tests/backend/test_parts_context_service.py`, `tests/backend/test_stream_endpoint.py`, `tests/backend/test_stream_api_perplexity.py`, `tests/backend/test_orchestration_service.py`, and `tests/backend/test_response_policy_service.py`.

#### Expected Output / Result

Conversation context, PARTS rewrite, and streaming behavior remain unchanged. Flat service files become small facades and related conversation code is discoverable under one package.

#### Testing Script

##### Act 01: Context Privacy Boundary

Build conversation context with a sensitive profile/memory setup.

Pass condition: prompt excludes unsupported learner-state claims and unsafe memory content as before.

##### Act 02: PARTS Rewrite Timeout

Configure a slow rewrite model call.

Pass condition: context assembly falls back without blocking beyond the existing timeout.

##### Act 03: Stream Tool Call

Simulate a stream response that includes a tool call and normal deltas.

Pass condition: SSE output and accumulator behavior match existing tests.

#### Gate to Enter the Next Phase

Run:

```bash
python -m py_compile backend/services/conversation_context_service.py backend/services/conversation_stream_service.py backend/services/parts_context_service.py backend/services/conversation/*.py
./backend/.venv/bin/python -m pytest tests/backend/test_conversation_context_service.py tests/backend/test_parts_context_service.py tests/backend/test_stream_endpoint.py tests/backend/test_stream_api_perplexity.py tests/backend/test_orchestration_service.py tests/backend/test_response_policy_service.py -q
wc -l backend/services/conversation_context_service.py backend/services/conversation_stream_service.py backend/services/parts_context_service.py backend/services/conversation/*.py
```

All commands must pass and every file must be at or below 657 lines.

#### Phase Commit

Commit message:

```text
refactor(conversation): group context stream and parts services
```

Stage only the three legacy service facades and `backend/services/conversation/`. Run staged checks and commit once.

### Phase 6: Consolidate Visual and Attachment Services

#### Problem

The previous split created focused visual subpackages, but flat files such as `visual_grounding_agent.py`, `visual_understanding_agent.py`, `visual_input_service.py`, `visual_affordance_registry.py`, `output_image_service.py`, `attachment_service.py`, and `attachment_image_storage_service.py` still sit directly under `backend/services/`. This makes `backend/services` look scattered even when file sizes are acceptable.

#### Assumptions

Existing imports from flat service modules must continue to work. Image-block schema, attachment validation, storage paths, data URI handling, visual affordance matching, and safe image logging are compatibility boundaries.

#### Solution

Create `backend/services/attachments/` and `backend/services/visual/` as domain packages. Move implementation classes into those packages while retaining the original flat files as compatibility facades. Fold previously created `visual_answer`, `pdf_visual`, and `paper_visual` packages under `visual` only if the team accepts import churn; otherwise document them as stable visual subdomains and avoid another move.

#### Implementation

> Context: Add Google-style docstrings documenting attachment trust boundaries, image storage ownership, visual verification semantics, and no-secret/no-data-URI logging. Inline comments should explain only validation gates, source provenance, and fallback choices.

Move attachment parsing/storage into `backend/services/attachments/`. Move visual affordance, grounding, understanding, and output-image internals into `backend/services/visual/`. Keep existing flat modules as import-compatible wrappers.

#### Expected File Tree After Phase 6

```text
backend/
└── services/
    ├── attachment_service.py            [modified]
    ├── attachment_image_storage_service.py [modified]
    ├── output_image_service.py          [modified]
    ├── visual_affordance_registry.py    [modified]
    ├── visual_grounding_agent.py        [modified]
    ├── visual_input_service.py          [modified]
    ├── visual_understanding_agent.py    [modified]
    ├── attachments/
    │   ├── __init__.py                  [new]
    │   ├── parsing.py                   [new]
    │   └── storage.py                   [new]
    └── visual/
        ├── __init__.py                  [new]
        ├── affordance.py                [new]
        ├── grounding.py                 [new]
        ├── input.py                     [new]
        ├── output.py                    [new]
        └── understanding.py             [new]
```

#### Work List

1. [ ] Create `backend/services/attachments/parsing.py`.
   - [ ] Move proposed attachment parsing and validation logic from `backend/services/attachment_service.py`.
2. [ ] Create `backend/services/attachments/storage.py`.
   - [ ] Move proposed image storage logic from `backend/services/attachment_image_storage_service.py`.
3. [ ] Create `backend/services/visual/affordance.py`.
   - [ ] Move proposed registry logic from `backend/services/visual_affordance_registry.py`.
4. [ ] Create `backend/services/visual/grounding.py`.
   - [ ] Move proposed `VisualGroundingAgent` internals.
5. [ ] Create `backend/services/visual/understanding.py`.
   - [ ] Move proposed `VisualUnderstandingAgent` internals.
6. [ ] Create `backend/services/visual/input.py` and `backend/services/visual/output.py`.
   - [ ] Move proposed visual input and output-image service internals.
7. [ ] Modify flat legacy service files.
   - [ ] Re-export public classes/functions and preserve patch paths.

#### Test Plan

Run `tests/backend/test_attachment_service.py`, `tests/backend/test_attachment_image_storage_service.py`, `tests/backend/test_visual_input_service.py`, `tests/backend/test_visual_grounding_agent.py`, `tests/backend/test_visual_understanding_agent.py`, `tests/backend/test_output_image_service.py`, `tests/backend/test_output_image_service_pdf_attachment.py`, `tests/backend/test_output_image_service_visual_retry.py`, and `tests/backend/test_visual_pipeline_integration.py`.

#### Expected Output / Result

Attachment and visual implementation code is grouped by domain folder while public imports continue to work. No image schema, PDF visual behavior, data URI handling, or storage behavior changes.

#### Testing Script

##### Act 01: Attachment Validation

Submit a valid PDF and an invalid oversized attachment through the existing attachment parser.

Pass condition: accepted and rejected cases match previous status and error behavior.

##### Act 02: Output Image Preparation

Prepare image blocks from verified visual candidates.

Pass condition: answer-block schema and retry behavior match current tests.

##### Act 03: Visual Grounding

Run visual grounding with mocked provider responses.

Pass condition: accepted/rejected source decisions remain unchanged.

#### Gate to Enter the Next Phase

Run:

```bash
python -m py_compile backend/services/attachment_service.py backend/services/attachment_image_storage_service.py backend/services/output_image_service.py backend/services/visual_affordance_registry.py backend/services/visual_grounding_agent.py backend/services/visual_input_service.py backend/services/visual_understanding_agent.py backend/services/attachments/*.py backend/services/visual/*.py
./backend/.venv/bin/python -m pytest tests/backend/test_attachment_service.py tests/backend/test_attachment_image_storage_service.py tests/backend/test_visual_input_service.py tests/backend/test_visual_grounding_agent.py tests/backend/test_visual_understanding_agent.py tests/backend/test_output_image_service.py tests/backend/test_output_image_service_pdf_attachment.py tests/backend/test_output_image_service_visual_retry.py tests/backend/test_visual_pipeline_integration.py -q
wc -l backend/services/attachment_service.py backend/services/attachment_image_storage_service.py backend/services/output_image_service.py backend/services/visual_affordance_registry.py backend/services/visual_grounding_agent.py backend/services/visual_input_service.py backend/services/visual_understanding_agent.py backend/services/attachments/*.py backend/services/visual/*.py
```

All commands must pass and every file must be at or below 657 lines.

#### Phase Commit

Commit message:

```text
refactor(visual): group attachment and visual services
```

Stage only the Phase 6 flat service facades and `backend/services/attachments/`, `backend/services/visual/`. Run staged checks and commit once.

### Phase 7: Service Directory Cleanup and Import Boundary Audit

#### Problem

After moving major domains into packages, `backend/services` may still contain a mix of small flat modules, compatibility facades, and true leaf services. Without an explicit cleanup phase, the directory can remain confusing even if no file is too long.

#### Assumptions

Compatibility facades are acceptable temporarily, but their purpose must be obvious. The project should avoid mass import rewrites that do not improve ownership. Any remaining flat file should either be a facade, a genuinely small cross-domain utility, or scheduled for a later plan.

#### Solution

Audit all `backend/services/*.py` files. Add package `__init__.py` exports where helpful, update internal imports to domain packages when low risk, and document remaining facade files. Do not remove facades until all internal and test imports have migrated.

#### Implementation

> Context: Add Google-style docstrings only for new public package exports or changed public helpers. Document compatibility facades and import-boundary rationale. Keep comments concise and focused on ownership boundaries.

Create `backend/services/README.md` or `docs/backend-services-structure.md` describing service domain folders, facade policy, and where new code should be placed. Optionally update internal imports from flat facades to domain packages only where tests show no patch-point dependency.

#### Expected File Tree After Phase 7

```text
backend/
└── services/
    ├── README.md                        [new]
    ├── answer_style_service.py          [modified if converted to facade]
    ├── cache_service.py                 [modified if moved or documented]
    ├── connection_manager.py            [modified if moved or documented]
    ├── explicit_memory_cache.py         [modified if moved or documented]
    ├── hot_memory_service.py            [modified if moved or documented]
    ├── memory_extraction_agent.py       [modified if moved or documented]
    ├── memory_retrieval_trace.py        [modified if moved or documented]
    ├── memory_semantic_analyzer.py      [modified if moved or documented]
    ├── response_boundary_validator.py   [modified if moved or documented]
    ├── turn_latency_trace.py            [modified if moved or documented]
    └── turn_plan_service.py             [modified if moved or documented]
```

#### Work List

1. [ ] Audit `backend/services/*.py`.
   - [ ] Classify each flat file as `compatibility facade`, `leaf utility`, or `future domain move`.
2. [ ] Create `backend/services/README.md`.
   - [ ] Document domain packages, facade policy, and placement rules for new service code.
3. [ ] Modify small flat files only when useful.
   - [ ] Move small memory-related leaf utilities into `backend/services/memory/` if the change is low risk and tests cover imports.
   - [ ] Move small runtime/connection utilities into an app or infrastructure package only if ownership is clear.
4. [ ] Update tests only for imports that intentionally move to a new public package.

#### Test Plan

Run the focused backend suite from the earlier phases and any tests for moved small utilities. Run `rg "from services\\.|import services\\." backend tests` to verify imports still resolve and there are no duplicate public entry points without documented facade intent.

#### Expected Output / Result

`backend/services` becomes a readable directory of domain folders plus documented compatibility facades and true small utilities. New code placement is documented and no existing behavior changes.

#### Testing Script

##### Act 01: Import Audit

Run `python -m py_compile` across all backend service modules.

Pass condition: every import resolves.

##### Act 02: Directory Classification

Read `backend/services/README.md` and compare it against `find backend/services -maxdepth 2 -type f -name '*.py'`.

Pass condition: every remaining flat service file is explained by the README.

##### Act 03: Focused Regression

Run the focused backend regression suite.

Pass condition: all tests pass or skip for the same environment reasons as before.

#### Gate to Enter the Next Phase

Run:

```bash
python -m py_compile backend/services/*.py backend/services/*/*.py
./backend/.venv/bin/python -m pytest tests/backend/test_answer_style_service.py tests/backend/test_cache_service.py tests/backend/test_hot_memory_service.py tests/backend/test_memory_ingestion_service.py tests/backend/test_turn_plan_service.py tests/backend/test_turn_intake_service.py -q
find backend/services -maxdepth 1 -type f -name '*.py' | sort
```

All commands must pass. The remaining flat service files must be documented as facades or leaf utilities.

#### Phase Commit

Commit message:

```text
docs(services): document backend service package boundaries
```

Stage only `backend/services/README.md` and any explicitly audited low-risk service moves from this phase. Run staged diff checks and commit once.

### Cross-Phase Regression and Final Acceptance

Run the full backend regression command available in the project:

```bash
npm run test:backend
```

If the full command is unavailable or environment-dependent, run the focused deterministic suite:

```bash
./backend/.venv/bin/python -m pytest tests/unit/test_orchestration_service.py tests/unit/test_gum_singleton.py -q
./backend/.venv/bin/python -m pytest tests/backend/test_stream_endpoint.py tests/backend/test_stream_api_perplexity.py tests/backend/test_orchestration_service.py tests/backend/test_rag_service.py tests/backend/test_attachment_service.py tests/backend/test_memory_store.py tests/backend/test_memory_store_compeer.py tests/backend/test_memory_source_boundaries.py tests/backend/test_compeer_scheduler.py tests/backend/test_compeer_integration.py tests/backend/test_conversation_context_service.py tests/backend/test_parts_context_service.py tests/backend/test_output_image_service.py tests/backend/test_visual_pipeline_integration.py -q
```

Manual or end-to-end scenario:

1. Start the backend with the existing development command.
2. Call `GET /api/v1/features`.
3. Send a normal `/api/v1/stream` chat request and verify SSE metadata, answer chunks, suggestions when configured, and terminal `[DONE]`.
4. Send a multipart `/api/v1/stream` request with a PDF and verify attachment visual sources reach orchestration.
5. Exercise memory list, candidate confirm/reject, memory edit, mailbox list/send/read, title generation, retrieve, proactive-check, and WebSocket notification ticket flows.

Final acceptance outcomes:

- `backend/main.py` is at or below 657 lines.
- Every modified production Python file is at or below 657 lines.
- `backend/services/` is organized around domain folders, and every remaining flat service file is either a documented compatibility facade or a true small leaf utility.
- Existing API routes, SSE event names/order, response schemas, auth dependencies, Redis/cache keys, background workers, notification payloads, mailbox semantics, and memory behavior remain unchanged.
- Existing patch paths used by tests continue to work through facades.
- Safe structured logging is preserved and does not include raw user text, prompts, attachments, generated model output, data URIs, credentials, tokens, or sensitive memory content.

Final Git review:

```bash
git status --short
git log --oneline -8
```

Expected phase commit order:

```text
refactor(app): extract backend bootstrap and runtime state
refactor(api): extract memory and mailbox routes
refactor(api): extract stream and utility routes
refactor(compeer): split scheduler domain modules
refactor(conversation): group context stream and parts services
refactor(visual): group attachment and visual services
docs(services): document backend service package boundaries
```

Remaining risks and mitigations:

- `backend.main` is heavily patched by tests, so route modules must resolve runtime state through compatibility providers instead of capturing stale imports. Mitigation: preserve facade exports and run stream tests after every route phase.
- FastAPI route registration can accidentally duplicate endpoints. Mitigation: inspect `app.routes` in tests or add a smoke assertion that each moved path appears once.
- SSE regressions are high impact. Mitigation: keep `/api/v1/stream` extraction in its own phase and block progress on terminal-event, content-type, or attachment parsing failures.
- ComPeer scheduler may contain event-loop-bound globals. Mitigation: split state ownership first, preserve legacy facade imports, and run ComPeer tests before touching unrelated services.
- Service directory cleanup can become churn. Mitigation: move only files with clear domain ownership and document the rest rather than forcing unnecessary import rewrites.
