# Backend service ownership

Put implementation in the domain that owns its behavior. Production Python
imports use `services.<domain>.<module>` with `backend/` on the import path.
Routes own HTTP validation and dependency injection; services own workflows and
provider requests. Keep `__init__.py` lightweight so importing data contracts does
not start providers or workers.

## Domain packages

| Package | Responsibility and entry point |
| --- | --- |
| `attachments/` | Parsing, validation and attachment storage. |
| `compeer/` | Proactive scheduling, care messages and background loops. |
| `conversation/` | `context.py` assembles prompts; `parts.py` builds task cards; `stream.py` owns streaming. Language, instruction rendering, memory recall, PARTS validation, image markers and provider request options have independent modules. |
| `memory/` | Memory eligibility (`gate.py`), typed hot entries (`hot.py`), extraction, semantic analysis, recall cache and retrieval tracing. |
| `memory/ingestion/` | `service.py` owns evidence eligibility and persistence order. `goals.py` completes uniquely matched goals; `preferences.py` validates extracted preferences. Rules, models and provider construction remain separate. |
| `memory/store/` | `service.py` owns the Redis store and process singleton; `behavior.py` and `candidates.py` own their existing Redis contracts. |
| `memory/gum/` | `runtime.py` owns instances, per-user initialization/reflection locks and worker handles. Reflection, compaction, ingestion and retrieval receive the runtime explicitly. Context and letters own model-facing work; `worker.py` owns the debounced queue. |
| `orchestration/` | `service.py` is the composition root. `execution.py` orders events and stages; `routing.py`, `response_policy.py`, `answer_preparation.py` and `completion.py` implement bounded phases alongside existing retrieval/prompting/streaming helpers. |
| `paper_visual/` | `planner.py` owns model/PDF I/O; `fallback.py` selects deterministic visuals; `validation.py` bounds plan output. |
| `pdf_visual/` | PDF geometry, extraction and rendering. |
| `query_policy/` | `classifier.py` owns model classification; `learning_guardrails.py` and `pdf_guardrails.py` enforce deterministic policy. |
| `realtime/` | Session configuration, OpenAI sessions, LiveKit token/dispatch, speech, attachments and bounded context. HTTP route registration lives in `app/routes/realtime/`. |
| `visual/` | Visual input, grounding, understanding and output coordination. |
| `visual_answer/` | `service.py` coordinates answer blocks. `preflight.py`, `slot_resolution.py` and `provider_preflight.py` own distinct retrieval workflows; clients, cache, scoring and layout retain their existing boundaries. |

## Dependency and state rules

- Orchestration constructs services and supplies callbacks. A stage must not look
  up its composition root through `sys.modules` or import a compatibility facade.
- GUM workflow functions receive their runtime dependency explicitly. Only
  `memory/gum/runtime.py` owns process state; do not copy its dictionaries or
  worker handles into another module.
- The memory store singleton lives only in `memory/store/service.py`.
- Visual mixins dispatch sibling helpers through `cls`/`self`. Do not inject the
  concrete service class into helper module globals.
- Pure language, validation and ranking helpers do not call providers.
- Preserve SSE event order, terminal events, Redis keys, user/conversation scope,
  memory provenance and optional-provider fallback behavior during refactors.
- Realtime services retain the existing voice-agent ownership. Anam renders the
  avatar only; LiveKit secrets and token minting remain server-side.
- Logs added to workflows contain event names, safe counters and error types;
  never include raw user text, prompts, provider output or credentials.

## Compatibility imports

The following legacy modules are aliases to the canonical implementation module,
so old and new imports share class identity, monkeypatches and mutable state:

| Legacy module | Canonical implementation |
| --- | --- |
| `gum_integration` | `services.memory.gum.runtime` |
| `memory_gate` | `services.memory.gate` |
| `memory_store` | `services.memory.store.service` |
| `services.memory_ingestion_service` | `services.memory.ingestion.service` |
| `services.memory_extraction_agent` | `services.memory.extraction` |
| `services.memory_semantic_analyzer` | `services.memory.semantic_analysis` |
| `services.memory_retrieval_trace` | `services.memory.retrieval_trace` |
| `services.hot_memory_service` | `services.memory.hot` |
| `services.explicit_memory_cache` | `services.memory.recall_cache` |
| `services.orchestration_service` | `services.orchestration.service` |
| `services.paper_visual_planner_service` | `services.paper_visual.planner` |
| `services.query_policy_service` | `services.query_policy.classifier` |
| `services.visual_answer_service` | `services.visual_answer.service` |

Both the listed legacy spelling and its `backend.` prefix resolve to the same
canonical module. New internal imports should use the canonical spelling.
Existing conversation, attachment, ComPeer and visual facades continue to expose
their previous APIs. Realtime's package root re-exports route functions and
historical helpers; tests that replace a helper must patch its owning service
module, not the router's re-export.

The unused helper packages `gum_parts/`, `memory_store_parts/` and
`services/memory_ingestion/` have been removed. Their implementations now live
under `services/memory/`.

Do not add business logic to compatibility modules. Remove an alias only after
all callers, tests and documented patch paths have migrated. Small cross-domain
services such as answer styling, turn tracing and connection management can
remain flat until they acquire a clear domain owner.

## Size and validation

Prefer cohesive modules around 150–350 lines. Review modules above 500 lines and
large functions for distinct responsibilities; do not split a cohesive function
solely to meet a line count. Do not create catch-all `utils` or `common` packages.

Run focused tests first, then the backend regression suite:

```bash
backend/.venv/bin/python -m pytest tests/backend/test_domain_refactor_contracts.py
backend/.venv/bin/python -m pytest tests/backend tests/unit --import-mode=importlib
```

`importlib` mode avoids existing duplicate test filenames across the two suites.
The domain contract tests cover shared legacy/canonical state, concurrent GUM
initialization and shutdown, HTTP route validation/dispatch, and incremental
image-marker parsing. Provider tests use mocks; passing them does not establish
live provider availability.
