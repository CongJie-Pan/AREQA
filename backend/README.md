# Backend layout

AREQA uses FastAPI routes, domain services, and a shared conversation runtime.
See [service ownership](services/README.md) for canonical module paths and
compatibility rules.

```text
backend/
  main.py                 Application entry and existing public bootstrap surface
  config.py               Server configuration
  auth.py                 Authentication
  redis_client.py         Shared Redis connection
  app/
    bootstrap.py          Application startup and service wiring
    runtime_state.py      Application runtime handles
    routes/
      realtime/           Session, speech, context and attachment HTTP routes
      ...                 Other API domains
  core/                   Conversation runtime, events, budgets and transport
  policies/               Cross-domain capability and memory policy
  agents/                 Agent decisions
  tools/                  Authorized tool boundaries
  prompts/                Shared prompt assets
  services/
    _compat/              Legacy flat import aliases only
    notifications/        WebSocket connection management
    retrieval/            Retrieval cache
    conversation/         Context, PARTS, language and model streaming
    orchestration/        Composition root and conversation execution stages
    realtime/             Voice/provider session and speech services
    memory/
      cold.py             Cold-memory retrieval (PostgreSQL + pgvector)
      scoring.py          Activation decay, STITCH tags and learner-state scoring
      gate.py             Memory eligibility gate
      ingestion/          Trusted evidence lifecycle
      store/              Redis memory persistence
      gum/                GUM lifecycle, workers and memory workflows
    query_policy/         Classification and deterministic guardrails
    paper_visual/         Semantic paper visual planning
    visual_answer/        Answer image retrieval, preflight and layout
    ...                   Existing attachment, ComPeer and visual domains
```

Memory code lives only under `services/memory/`; import and patch it by its
canonical path (for example `services.memory.store.service`). The former flat
modules (`memory_store.py`, `gum_integration.py`, `memory_gate.py`,
`cold_memory.py`, `compaction.py`) were removed. Selected flat
`services/_compat/*_service.py` modules still contain compatibility imports only.

This organization does not relocate independent infrastructure such as the job
store. Move it only with a separate review of its consumers and storage contracts.

## Reorganization validation

The domain reorganization was checked with the existing behavior tests plus
regressions for import identity, GUM initialization/shutdown, HTTP dispatch,
stream marker boundaries, database location, and observation metadata pruning.

- Initial domain regression set: **392 passed, 6 skipped**.
- Service layout/import contracts: **14 passed**, including all 35 legacy
  aliases in three fresh-process import orders and image prompt asset loading.
- Full `tests/backend` and `tests/unit` run using `--import-mode=importlib`:
  **920 passed, 7 skipped, 6 failed** (after the service-root cleanup).
  The immediate pre-cleanup baseline was **917 passed, 7 skipped, 6 failed**;
  the failing test names are unchanged.
- Changed Python files compile successfully. Ruff's `F821`, `F822`, `F823` and
  `E9` checks pass; these are targeted correctness checks, not a claim that the
  whole repository passes every lint rule.
- No live provider/deployment test was performed.

The following failures also reproduce against pre-refactor commit `e05cd74` and
remain outside the domain reorganization:

| Test file | Failing test |
| --- | --- |
| `tests/backend/test_edf_integration.py` | `test_compeer_daily_schedule_e2e` |
| `tests/backend/test_generate_title.py` | `test_generate_title_uses_english_for_english_first_query` |
| `tests/backend/test_suggestion_service.py` | `test_suggestion_service_uses_latest_query_language_for_english_suggestions` |
| `tests/backend/test_suggestion_service.py` | `test_suggestion_service_accepts_concise_english_questions_over_old_limit` |
| `tests/unit/test_auth_jwt.py` | `test_optional_auth_verifies_supplied_credentials` |
| `tests/unit/test_cold_memory_pg.py` | `test_cold_memory_search_pg` |

The cold-memory failure appears in the combined suite and passes in a smaller
selection, indicating an existing test-order dependency. These six failures
need separate resolution before treating the full backend suite as green.
