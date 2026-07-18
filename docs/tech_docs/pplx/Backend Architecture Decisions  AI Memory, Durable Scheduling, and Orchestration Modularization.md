# Backend Architecture Decisions: AI Memory, Durable Scheduling, and Orchestration Modularization

> Advisory report for an AI learning companion application. Three design problems identified in a July 16 experiment: (1) incorrect durable memory promotion, (2) a Redis-dependent scheduler that can lose care-letter delivery, and (3) a 1,000+ line orchestration service with mixed concerns. Fourteen propositions are assessed below.

***

## Part 1 — Durable Profile Memory

### Proposition 1 · Durable profile memory should require stable provenance fields (user_id, message_id, conversation_id, timestamp, raw user text, source role)

**Recommendation: Accept.**

This is established best practice in production AI memory systems. The Eywa architecture (2026) defines an *evidence-before-belief* invariant: every writable memory must be linked to an immutable source record that carries user scope, role, time, and verbatim text before any LLM-derived fact is promoted. The provenance fields you list map precisely to those requirements.[^1]

- `user_id` and `conversation_id` enforce scope isolation, preventing cross-user and cross-session memory leakage.[^2]
- `message_id` and `timestamp` support temporal reasoning, revision tracking, and deletion by the evidence owner.[^1]
- `raw user text` as an immutable evidence anchor ensures extracted beliefs can be audited, repaired, or re-extracted without losing the original source.[^1]
- `source role` (user vs assistant vs system) is the most critical field for your reported failure. A question like "What learning method do I prefer?" carries role `user` but has interrogative syntax; if role is absent, no downstream rule can distinguish it from a declarative assertion.[^2]

**Tradeoffs.** Requiring all six fields before promotion adds a write-path validation step and may reject candidates that arrive from legacy pipes without full metadata. The cost of a rejected write is low (the fact is preserved as a pending candidate); the cost of an accepted write with bad provenance is silent behavioral pollution across future sessions.[^3]

**Your code.** `memory_gate-3.py`'s `extract_user_memory_candidates` already filters to `role == user` messages and requires `evidence_quote` to be present in the source text, which is the right structural pattern. The missing controls are upstream: neither `classify_user_message` nor `apply_user_message_gate` passes `message_id` or `source_role` into the memory store operation, so the store receives explicit memory writes with weaker provenance than the extractor generates.

***

### Proposition 2 · Automatic memory promotion should fail closed when provenance is incomplete

**Recommendation: Accept.**

A fail-closed default ("deny if provenance incomplete") is the only option that keeps durable memory trustworthy. AI agent memory security guidance is explicit: *a memory write should be a structured event, not an accidental side effect of summarization*. Incomplete provenance is evidence that the candidate originated outside a verified user turn — exactly the failure class your retention-policy function is supposed to block.[^2]

**Failure mode of fail-open.** If promotion succeeds with partial provenance, the store accumulates entries whose evidence chain cannot be reconstructed. When those entries later influence prompt context, post-turn reflection, or cold memory retrieval, downstream answers are shaped by unauditable state — which is indistinguishable from a poisoned memory attack.[^3][^2]

**Implementation note.** `evaluate_memory_retention_policy` already checks for empty text and sensitive keywords. Add a provenance-completeness check as the first predicate, returning `MemoryRetentionDecision("deny", "incomplete_provenance")` when any required field is absent. This is a one-line addition that closes the gap without touching the rest of the policy chain.

***

### Proposition 3 · Legacy memory candidates without provenance should require explicit user confirmation rather than automatic migration

**Recommendation: Accept — require explicit confirmation, do not migrate automatically.**

Legacy candidates that lack full provenance are structurally unverifiable. Migrating them automatically would backfill the store with entries that cannot satisfy any future audit or erasure request. Production memory governance literature recommends starting with explicit user-confirmed memory only and expanding only after provenance infrastructure is in place.[^1][^2]

**Practical approach:**
1. Mark existing candidates as `status = pending_confirmation` without promoting them.
2. Surface a lightweight confirmation flow ("We noticed you may prefer X — is that right?") the next time the user is active.
3. On confirmation, write the full provenance record with `source_role = user_confirmation` and the confirmation timestamp.
4. Candidates that remain unconfirmed for a configurable TTL (e.g., 90 days) should expire and be dropped.

**Tradeoff.** Explicit confirmation increases friction and may result in valuable preferences never being confirmed if users dismiss the prompt. An alternative is to retain legacy candidates in a read-only "soft context" layer that influences prompt assembly but is never persisted as durable profile memory — this provides utility without creating unauditable writes.

***

### Proposition 4 · Embeddings and model classifiers should assist semantic matching but should not independently authorize durable memory writes

**Recommendation: Accept — strongly.**

This is one of the clearest consensus positions in production AI agent architecture. The architectural argument from multiple independent sources is the same: LLMs and classifiers are non-deterministic. The same input can produce different outputs across runs, and their outputs are manipulable by adversarial content in the context. An authorization gate that can be argued with in natural language is not an authorization gate.[^4][^5][^2]

The correct split:[^4]
- **LLMs / classifiers / embeddings**: soft advisory work — extract candidates, score confidence, detect anomalies, suggest categories, perform semantic matching for retrieval.
- **Deterministic policy engine (code rules)**: hard binary permit/deny for the write itself, based on structured fields: `source_role == user`, `confidence >= threshold`, `category in allowed_set`, `sensitive_keywords absent`.

The "Trinity Defense Architecture" and Google DeepMind's CaMeL independently reach the same conclusion: the model suggests, the system decides.[^5][^4]

**Your code.** `evaluate_memory_retention_policy` already implements this split correctly in spirit — it runs deterministic rule checks after candidate extraction. The gap is that the `candidate_only` outcome path does not enforce a hard gate before eventual write, and `classify_reflection_insight` promotes session reflections (LLM-generated text) to `should_cold_store = True` without a deterministic confirmation step.

***

### Proposition 5 · A legacy retention-policy class should be removed only after all runtime callers are migrated, or retained temporarily as a compatibility adapter

**Recommendation: Accept — retain as compatibility adapter, remove after full caller migration.**

Immediate removal of an internal module while callers exist is a common cause of silent regressions in production services. Martin Fowler's Strangler Fig pattern and standard monolith decomposition advice both recommend progressive migration with the old code serving as an adapter boundary until all callers are migrated. Removing a class before its callers are migrated forces them to either fail at runtime or bypass the intended policy layer entirely, which is worse than the legacy behavior.[^6][^7]

**Recommended migration path:**
1. Mark the legacy class `@deprecated` and log a warning on every invocation.
2. Add a thin wrapper that calls the new provenance-gated policy under the legacy interface.
3. Migrate callers one at a time, replacing the legacy import with the new function.
4. Remove after all callers are verified and at least one full deployment cycle has passed with no deprecation warnings.

***

## Part 2 — ComPeer / Delayed Care-Letter Scheduling

### Proposition 6 · The database should be the source of truth for delayed mail tasks, with Redis only as an accelerator

**Recommendation: Accept.**

This is the standard "outbox + queue" architecture for durable delayed job delivery. The database (PostgreSQL, SQLite, or equivalent) provides ACID guarantees, survives process restarts and Redis failures, and holds the authoritative state of every task. Redis acts as a dispatch accelerator — a sorted set indexed by delivery timestamp — whose contents are a *projection* of the DB, not the primary record.[^8][^9][^10]

> "Redis is fantastic at what it does — being a cache and fast data store. But when you need reliable scheduling, reach for a proper scheduler." — Production engineering consensus[^11]

**Your code.** `compeer_scheduler-2.py` calls `mb_store.schedule_delayed_mail` (which presumably writes to a DB-backed mailbox store) and also clears `trigger_proactive` from hot memory (Redis-backed) before the DB write result is awaited. This creates a race: if `schedule_delayed_mail` fails or times out, the trigger has already been erased and the task is silently lost.

***

### Proposition 7 · Redis-only delayed delivery should be treated as degraded mode, not reliable delivery

**Recommendation: Accept.**

Redis TTL-based scheduling is documented as an anti-pattern for production scheduling. Key expiry notifications are delivered in the background with no timing guarantees under load, and a Redis restart without AOF/RDB enabled loses all pending entries permanently. Even with persistence enabled, Redis offers at-most-once semantics without additional idempotency controls. Redis sorted-set polling (ZRANGEBYSCORE) is a legitimate accelerator pattern, but it is reliable only when the DB is the backup source of truth.[^12][^13][^14][^11]

**Failure modes of Redis-only delivery:**
- Redis process restart: all pending tasks lost unless RDB/AOF is configured.
- Redis OOM: eviction policies may discard task entries silently.
- Network partition: scheduler loop cannot read queue; tasks pile up with no reconciliation path.
- Worker crash after ZREM but before processing: task disappears without being delivered.

***

### Proposition 8 · Proactive triggers should be cleared only after durable task persistence succeeds

**Recommendation: Accept.**

The current code in `proactive_scheduler_loop` deletes `trigger_proactive` from hot memory and then calls `schedule_areqa_care_letter`, which internally calls `mb_store.schedule_delayed_mail`. The `del hot_mem[key]` and Redis write happen before the DB-backed task creation is confirmed. This is a classic dual-write problem — the exact problem the transactional outbox pattern exists to solve.[^9][^15][^8]

**Correct sequence:**
```python
# 1. Read trigger from hot_mem (do NOT delete yet)
trigger_data = hot_mem.get("trigger_proactive")
# 2. Persist task durably (DB write)
task_id = await schedule_areqa_care_letter(...)
# 3. Only on confirmed DB write, clear the trigger
del hot_mem["trigger_proactive"]
await store.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(hot_mem))
```
If the DB write fails, the trigger remains intact and the scheduler loop will retry on the next tick.

***

### Proposition 9 · LLM generation failure before task persistence should keep the trigger retryable with bounded exponential backoff

**Recommendation: Accept.**

LLM failures (network timeout, 5xx, rate limit) before a task record exists are transient by nature. The correct handling is to leave the trigger in place and reschedule with exponential backoff and jitter. AWS Well-Architected guidance for agentic AI explicitly recommends exponential backoff with full jitter, failure-type-specific retry counts, and circuit breakers at two levels — per invocation and cross-invocation — to prevent retry storms.[^16][^17][^18]

**Recommended policy for care-letter LLM failures:**
- Classify LLM 429 / 503 / timeout as retryable; validation errors and empty-message cases as non-retryable.
- Backoff: `delay = min(base_delay × 2^attempt + jitter, max_delay)` with `base_delay = 30s`, `max_delay = 1800s` (30 min).
- Max attempts: 3–5 before writing a `failed` status to the task table and clearing the trigger.
- Jitter: full jitter (`random.uniform(0, delay)`) or equal jitter to spread load across users.[^17][^19]
- Log every attempt with retry count, error type, and delay for monitoring.

Do not clear the trigger on failure. Clear it only when the task is either durably persisted or has exhausted retries.

***

### Proposition 10 · The delayed worker should periodically reconcile DB tasks into Redis, and use deterministic task IDs for idempotency

**Recommendation: Accept — both parts.**

**Reconciliation.** A periodic reconciler (every 60–300 seconds) scans the DB for tasks in `status = pending` with `deliver_at <= now + lookahead_window` and adds their IDs to the Redis sorted set using `ZADD NX` (no-overwrite). This heals divergence caused by Redis failures, worker restarts, or missed enqueue events. Tasks already in the sorted set are not re-added due to `NX`, so the operation is idempotent.[^10][^8]

**Deterministic task IDs.** `compeer_scheduler-2.py` already implements `_stable_task_id` using SHA-256 over `(user_id, event_summary, date_bucket)`. This is the correct pattern: if the same trigger fires twice (e.g., a retry), `ZADD NX task_id score` will silently skip the duplicate because the ID already exists in the sorted set. The DB insert should also use an `ON CONFLICT DO NOTHING` clause on `task_id` to prevent duplicate rows.[^13][^20]

**What can still go wrong.** Deterministic IDs based on `date_bucket` (daily granularity) mean two distinct care-letter events on the same day for the same user will collide if their `event_summary` is identical. Consider including a finer-grained component such as the trigger timestamp (hour-bucketed) or `run_id` when higher daily frequency is needed.

***

### Proposition 11 · Task IDs should be deterministic/idempotent to prevent duplicate care letters

**Recommendation: Accept — already partially implemented, needs DB-level enforcement.**

`_stable_task_id` already hashes `(prefix, user_id, event_summary, date_bucket)` to a 32-character hex string. This is exactly the approach used in production deduplication systems: a stable, reproducible key that makes a duplicate insertion a no-op. The remaining gap is ensuring the DB table enforces `UNIQUE(task_id)` and the insert uses `ON CONFLICT DO NOTHING` or `ON CONFLICT DO UPDATE SET status = EXCLUDED.status WHERE status = 'pending'` to allow status transitions without creating duplicates.[^20][^13]

***

## Part 3 — Orchestration Service Modularization

### Proposition 12 · The SSE streaming event sequence should remain a hard compatibility contract during refactor

**Recommendation: Accept — treat as a public API contract, not an implementation detail.**

The `OrchestrationService.execute` method in `orchestration_service.py` yields a sequence of SSE events (`metadata`, `status`, `action`, `toolstarted`, `toolcompleted`, `sources`, `generating`, `suggestions`, `done`) that the frontend client parses and renders. This sequence is already an implicit protocol. Changing it during a refactor would silently break the client, and SSE streams are notoriously difficult to version because the client cannot negotiate a schema the way it can with a REST endpoint.

The Strangler Fig migration pattern and standard microservice decomposition guidance both treat existing external contracts as migration anchors: extract internal implementation, preserve the external interface. For streaming services, this means the new domain services write to the same `sseadapter.encode` calls inside the existing transport layer, not to a new transport.[^7][^6]

**Practical rule:** `SSE event type + payload schema = breaking change if modified`. Any new event type should be additive (the client ignores unknown types), and no existing event type should be removed until clients have been migrated. Document the sequence as a versioned contract (e.g., `streaming-contract-v1`) and add an integration test that asserts the full sequence is emitted for a sample request.

***

### Proposition 13 · Refactoring should prioritize clear service boundaries before aggressive line-count reduction

**Recommendation: Accept.**

Line count is a symptom of mixed concerns, not a root cause. Aggressive line reduction without prior boundary definition typically produces a smaller file that still mixes the same concerns — harder to read, equally hard to test, and still monolithic. The canonical decomposition advice from Netflix and Domain-Driven Design practitioners is: identify bounded contexts first, align services to those contexts, then migrate incrementally.[^21][^6][^7]

The `OrchestrationService` in `orchestration_service.py` spans at least five distinct domains that each have different change rates, different failure modes, and different owners:

| Domain | Current location | Change trigger |
|--------|-----------------|---------------|
| Search routing / RAG | `node_rag_retrieval`, `node_perplexity_search` | Search index changes, Perplexity API changes |
| Prompt/context assembly | `node_prompt_assembly` | System prompt changes, memory format changes |
| LLM stream + tool dispatch | `node_llm_stream` | Model changes, tool additions |
| Memory side effects | Inline in `execute` | Memory policy changes |
| Post-turn jobs | `node_post_generation`, inline `asyncio.create_task` | Suggestion model changes, reflection policy changes |

Extracting these into dedicated services before reducing line count gives you independently testable units, clear ownership, and the ability to change one domain without touching the others.[^21][^7]

***

### Proposition 14 · Recommended service boundaries for memory ingestion, prompt/context preparation, post-turn jobs, delayed scheduling, and streaming control

**Recommendation: Five named service boundaries, one transport layer.**

| Service | Responsibility | Boundary rule |
|---------|---------------|--------------|
| **MemoryIngestionService** | Classify user message, apply provenance gate, write to memory store | Does not read prompt state. Never called inside the SSE hot path. |
| **ContextAssemblyService** | Fetch hot memory snapshot, assemble system prompt, inject RAG/web context | Reads only; no writes. Returns a `PromptContext` value object. |
| **SearchOrchestrator** | RAG retrieval + Perplexity search, reranking, source event emission | Emits to `sseadapter`; does not write memory. |
| **PostTurnService** | Reflection observation, EDF evaluation, suggestion generation | Always async; never blocks the SSE stream. Receives `(user_id, conversation_id, answer_text, context_results)`. |
| **DelayedSchedulingService** | Persist care-letter tasks to DB, enqueue to Redis, manage reconciliation | Owns the outbox table. Accepts a `TaskRequest` and returns `task_id`. `ComPeerScheduler` calls this service; it does not call Redis directly. |
| **StreamingController** (existing `OrchestrationService`) | Session lifecycle, SSE transport, composing the above services in sequence | Becomes a thin conductor: starts session, delegates to each service, encodes events, closes session. |

**Migration strategy (Strangler Fig):**

1. Extract `MemoryIngestionService` first — it has the clearest boundary and the most urgent correctness problem (provenance gating).
2. Extract `PostTurnService` second — it is already partially async (`asyncio.create_task`) and has no SSE coupling.
3. Extract `ContextAssemblyService` — this is read-only and safe to test in isolation.
4. Extract `DelayedSchedulingService` — required before the ComPeer Redis fix can be properly isolated.
5. Leave `SearchOrchestrator` embedded or extracted last, as it has the tightest SSE coupling (emits `sources` and status events inline).

**Anti-patterns to avoid:**
- Do not extract a service that must be called synchronously inside the SSE yield loop without careful latency budgeting — adding a network hop to the hot path will increase p99 stream latency.[^21]
- Do not share a database connection pool across service boundaries in the same process without connection count planning.
- Do not extract `DelayedSchedulingService` as a separate process until the DB outbox and reconciler are in place — otherwise a process-boundary call failure recreates the same durability gap.[^8][^10]

***

## Summary Decision Table

| # | Proposition | Verdict | Key risk if rejected |
|---|-------------|---------|----------------------|
| 1 | Require provenance fields for durable profile memory | **Accept** | Unauditable memory writes; scope leakage |
| 2 | Fail closed when provenance incomplete | **Accept** | Silent poisoning of profile memory |
| 3 | Legacy candidates require user confirmation | **Accept** | Unverifiable entries in durable store |
| 4 | Classifiers assist; deterministic rules authorize | **Accept** | Non-deterministic write authorization; prompt-injection attack surface |
| 5 | Retain legacy class as adapter until callers migrated | **Accept** | Silent runtime bypass of policy layer |
| 6 | DB = source of truth; Redis = accelerator | **Accept** | Care letters lost on Redis failure |
| 7 | Redis-only delivery = degraded mode | **Accept** | False reliability assumption in scheduler |
| 8 | Clear trigger only after DB write confirmed | **Accept** | Lost triggers; missed delivery |
| 9 | LLM failure before persistence → bounded backoff, trigger retained | **Accept** | Trigger consumed, task never created |
| 10 | Periodic DB→Redis reconciler + deterministic IDs | **Accept** | Divergence accumulates; duplicates on retry |
| 11 | Task IDs deterministic + DB UNIQUE constraint | **Accept** | Duplicate care letters to same user |
| 12 | SSE sequence = hard streaming contract | **Accept** | Silent client breakage during refactor |
| 13 | Boundaries before line-count reduction | **Accept** | Smaller monolith, same coupling problems |
| 14 | Five service boundaries + thin controller | **Accept** | Mixed-concern tests; cascading changes |

---

## References

1. [Eywa: Provenance-Grounded Long-Term Memory for AI Agents](https://arxiv.org/pdf/2605.30771.pdf)

2. [AI Agent Memory Security Controls for Production Agents](https://aipromptgear.com/agent-systems/ai-agent-memory-security-controls-for-production-agents/) - How to secure AI agent memory with provenance, write gates, retrieval checks, audit events, rollback...

3. [Memory Privacy and Retention for Persistent AI Agents](https://zylos.ai/research/2026-04-28-memory-privacy-retention-persistent-ai-agents/) - How persistent AI agents should govern memory retention, deletion, provenance, consent, and workspac...

4. [AI Agent Authorization: Don't Let the LLM Decide](https://fp8.co/articles/AI-Agent-Authorization-LLM-vs-Policy-Engine) - Using an LLM to authorize agent actions duplicates your attack surface. Why deterministic policy eng...

5. [[Revue de papier] Trustworthy Agentic AI Requires Deterministic ...](https://www.themoonlight.io/fr/review/trustworthy-agentic-ai-requires-deterministic-architectural-boundaries) - Current agentic AI architectures are fundamentally incompatible with the security and epistemologica...

6. [How to break a Monolith into Microservices](https://martinfowler.com/articles/break-monolith-into-microservices.html) - In this write-up, I share a few techniques that can guide the delivery teams - developers, architect...

7. [Determining Service Boundaries and Decomposing Your ...](https://www.cerbos.dev/blog/determining-service-boundaries-and-decomposing-monolith) - In this 10-part series, we'll guide you through the most common challenges faced during monolith to ...

8. [The Transactional Outbox Pattern: From a Single Task to a ...](https://codewithkyryl.dev/2026/06/07/outboxes/) - A practical guide to the Transactional Outbox Pattern in Java, Spring Boot and PostgreSQL — solving ...

9. [The Transactional Outbox Pattern: Reliable Event Publishing](https://james-carr.org/posts/2026-01-15-transactional-outbox-pattern/) - How to guarantee event delivery without distributed transactions using the Transactional Outbox patt...

10. [Transactional Outbox Pattern in Laravel: Ensuring Data Consistency](https://rubel.dev/blog/transactional-outbox-pattern-in-laravel-ensuring-data-consistency) - Master the Transactional Outbox pattern in Laravel to prevent data loss. Learn how to bridge databas...

11. [Evan King's Post](https://www.linkedin.com/posts/evan-king-40072280_just-use-redis-ttl-for-scheduling-is-the-activity-7274541015770808320-5wbJ) - "Just use Redis TTL for scheduling" is the kind of solution that sounds brilliant at 2 PM in a desig...

12. [Recurring Jobs (Cron-like...](https://oneuptime.com/blog/post/2026-01-21-redis-job-scheduling/view) - A comprehensive guide to implementing job scheduling with Redis, covering delayed jobs, recurring ta...

13. [Redis Delayed Queue: ZSET + Timestamp Pattern](https://kveditor.com/blog/redis-delayed-queue) - Build a reliable delayed queue with Redis Sorted Sets and timestamps. Covers scheduling, polling, at...

14. [How to Build a Delayed Job Queue with Redis - OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-delayed-job-queue/view) - Build a Redis delayed job queue using sorted sets to schedule jobs for future execution and poll for...

15. [Tackling the Dual-Write Dilemma: The Transactional ...](https://engineering.getmidas.com/tackling-the-dual-write-dilemma-the-transactional-outbox-pattern-ca8f974154b8) - The Outbox pattern effectively tackles the dual-write problem by introducing an intermediary “outbox...

16. [Building a Retry System with Exponential Backoff for LLM API Calls ...](https://dev.to/german_yamil_e021eef8710d/building-a-retry-system-with-exponential-backoff-for-llm-api-calls-in-python-3imf) - A complete Python retry system for LLM APIs — exponential backoff with jitter, Retry-After header ha...

17. [What Is a Retry Strategy? FutureAGI Guide (2026)](https://futureagi.com/glossary/retry-strategy/) - Design retry strategies for LLM and tool calls: exponential backoff, idempotency keys, jitter, and c...

18. [agentrel07-bp02.md](https://docs.aws.amazon.com/ja_jp/wellarchitected/latest/agentic-ai-lens/agentrel07-bp02.md)

19. [When to use exponential...](https://betterstack.com/community/guides/monitoring/exponential-backoff/) - This article explores exponential backoff from first principles, providing practical implementations...

20. [Writes done Right : Atomicity and Idempotency with Redis, Lua, and ...](https://dev.to/pixperk/writes-done-right-atomicity-and-idempotency-with-redis-lua-and-go-5ebd) - Life would have been easy if the world were filled with monolithic functions. Simple functions that....

21. [DRAFT](https://dev.to/jungledev/draft-1pcp) - Decision Framework When to Extract a Service Score each potential service extraction: Business...

