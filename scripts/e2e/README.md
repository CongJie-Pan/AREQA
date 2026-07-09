# Cloud API Probe

This directory contains manual cloud probes that must not run in normal CI.
They read the repository `.env`, call the configured AREQA API, and inspect
cloud Redis/PostgreSQL data paths with a generated test user.

## Preflight

```bash
python scripts/e2e/cloud_api_probe.py
```

The preflight checks:

- Required `.env` keys exist, without printing secret values.
- Redis can be reached through `REDIS_URL`.
- PostgreSQL can be reached through `DATABASE_URL`.
- Cold-memory schema availability: `public.propositions` and `public.vec_memory`.
- Mailbox persistence schema availability: `public.mailbox_messages` and
  `public.mailbox_delayed_tasks`.
- Backend API auth behavior for `/api/v1/mailbox` and `/api/v1/memory`.

If the preflight reports `PostgreSQL propositions table` as failed, apply:

```text
supabase/migrations/20260709_cold_memory_schema.sql
```

Run it in the Supabase SQL editor for the target project, then rerun the
preflight.

If the preflight reports either mailbox table as failed, apply:

```text
supabase/migrations/20260709_mailbox_persistence_schema.sql
```

The mailbox tables make Supabase/PostgreSQL the source of truth for user-visible
mail and scheduled delivery metadata. Redis is still used for cache, delayed
queue, locks, and fast worker polling.

If authenticated API calls return `Auth configuration missing`, configure
`JWT_SECRET` in the running backend environment and redeploy/restart the API.

## Write Probe

```bash
python scripts/e2e/cloud_api_probe.py --write --skip-delayed-wait
```

This writes isolated test data with a generated `TEST_USER_ID` and `RUN_ID`,
then verifies:

- `POST /api/v1/log_action` writes hot memory to Redis.
- Multiple `log_action` events are sent by default so GUM batch processing can
  produce cold-memory propositions.
- `POST /api/v1/mailbox/send` writes a user mail.
- Redis contains the mailbox and delayed queue records.
- PostgreSQL contains matching mailbox message and delayed task rows.
- PostgreSQL contains a matching proposition when cold-memory processing works.

The default cleanup removes only the generated test user's Redis keys and
matching PostgreSQL mailbox/cold-memory rows.

## Full Delayed Mail Probe

```bash
python scripts/e2e/cloud_api_probe.py --write
```

This waits up to 420 seconds for the delayed mailbox worker to deliver the
avatar reply and verifies it is not duplicated.

## Useful Overrides

```bash
python scripts/e2e/cloud_api_probe.py \
  --backend-url http://localhost:8000 \
  --test-user-id 00000000-0000-0000-0000-000000000001 \
  --run-id api-e2e-manual-001
```

Use `--backend-url http://localhost:8000` when running the backend locally with
cloud `.env` values. This validates the same cloud Redis/PostgreSQL paths while
avoiding Render environment drift.

Use `--memory-events N` to change how many `log_action` events are sent during
the write probe. The default is `18` because the GUM observer batches
observations before creating long-term propositions.
