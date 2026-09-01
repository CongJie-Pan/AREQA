## Root Cause Categorization

The reported slowness is architectural, not incidental — the current flow makes the UI's first paint dependent on a full network round-trip and full-table diff before anything renders. This can be decomposed into four distinct root causes:

1. **Blocking initialization order (critical path bug).** The app awaits `fetchConversations → fetchMessages → merge → loadConversations()` before ever touching the Zustand store, so the sidebar is gated by the slowest external dependency (network + Supabase) rather than the fastest one (Dexie/IndexedDB, which is local and near-instant).[^1][^2]
2. **Unbounded, non-incremental fetches.** `.select('*').eq('user_id', userId)` with no `.order()`, `.range()`, or `updated_at` filter re-downloads the entire conversation and message history on every refresh, and is silently capped at Supabase's default 1,000-row limit (`db-max-rows`), which means large histories can be truncated without any error.[^3][^4][^5]
3. **O(n) client-side merge cost.** Diffing "all cloud rows" against "all local rows" every time is a linear-growing bottleneck — cost scales with total lifetime message count, not with what actually changed since the last sync.[^6]
4. **No separation of concerns between metadata and payload.** Conversations (small, frequently needed for the sidebar) and messages (large, only needed per-open-conversation) are fetched and merged together, so opening the sidebar pays the cost of loading every message body in every conversation.[^2][^7]

## Recommended Architecture Design

The standard fix used by local-first chat/productivity apps (Linear, Notion, WhatsApp Web, Dexie Cloud-based apps) is to make **Dexie the primary read source for the UI** and treat Supabase purely as a background reconciliation target — never a blocking dependency for first paint. Concretely:[^8][^7][^2]

- **On app/store hydration:** Zustand's `loadConversations()` reads directly from Dexie (or is driven by a Dexie `liveQuery`) and paints the sidebar immediately, with zero network dependency.[^7][^2]
- **In parallel, not before:** kick off a background sync worker that pulls only *changed* rows from Supabase using an `updated_at` cursor, merges them into Dexie, and lets the reactive Dexie query re-render the store automatically.[^2][^7]
- **Split sync scopes:** a lightweight "conversations" sync (small rows: id, title, updated_at, last_message_preview) runs on every load; a heavier "messages" sync is deferred and scoped to the conversation the user actually opens.[^2]
- **Lazy-load messages per conversation.** Only fetch/hydrate message rows for a conversation when the user selects it, using its own `updated_at` cursor and pagination, rather than syncing the entire message table upfront.[^6][^2]

This is a textbook application of the **Stale-While-Revalidate (SWR)** pattern combined with **offline-first/local-first architecture**: serve the cached (stale) local copy instantly, then revalidate against the network and reconcile in place. Several production Dexie-based apps (Dexie Cloud Starter, Hunter Vault, ParkManager) implement exactly this "local read → background push/pull → reactive UI" loop.[^9][^1][^7]

## Trade-off Comparison of Proposed Solutions

| Approach | First-paint latency | Implementation effort | Data freshness | Notes |
|---|---|---|---|---|
| Current (sync-then-load) | Poor — blocked by full network round trip | None (status quo) | High (always fresh) | Root cause of the reported issue [^2] |
| Local-first load + background full sync | Excellent — instant paint from Dexie | Low–Medium | Medium (brief staleness window) | Good short-term fix; still re-fetches everything in background [^1][^7] |
| Local-first + incremental cursor sync (`updated_at`) | Excellent | Medium | High, with minimal lag | Recommended long-term baseline; avoids re-scanning full history [^6][^10] |
| Split conversation/message sync + lazy message load | Excellent, and keeps sidebar sync cheap indefinitely | Medium | High for conversations; on-demand for messages | Addresses the "grows expensive over time" bottleneck directly [^2] |
| CRDT-based sync (e.g., Loro, Automerge, Yjs) | Excellent, plus robust multi-device conflict resolution | High | High, conflict-free by construction | Overkill unless true concurrent multi-device editing of the same conversation is a requirement [^11][^12] |
| Increase Supabase max-rows / raise `.limit()` | No improvement to latency | Trivial | Same | Does not fix root cause; only avoids silent truncation, and larger payloads make queries slower [^4][^5] |

## Minimum Viable Fix (Short-Term)

These changes can typically ship within a day and remove the blocking behavior without a full sync-engine rewrite:

- Reorder initialization: call `loadConversations()` from Dexie synchronously (or via a Dexie `liveQuery` subscription) on mount, then fire the Supabase sync as a non-blocking background task (`void syncFromCloud()`), so the UI never awaits the network.[^1][^2]
- Add explicit `.order('updated_at', { ascending: false })` and `.range()`/`.limit()` to every Supabase query — the 1,000-row cap is a **server-side hard limit** that silently truncates unordered results, so this is a correctness fix as much as a performance one.[^4][^5][^3]
- Fetch only conversation metadata on load; defer the messages query entirely until a conversation is opened.[^2]
- Add a `last_synced_at` value (per user, stored in Dexie or `localStorage`) and filter the Supabase pull with `.gt('updated_at', lastSyncedAt)` instead of pulling the entire table every time.[^10][^6]
- Merge incoming rows into Dexie via `bulkPut` keyed on primary id rather than clearing and re-inserting the whole table, so the reactive query only re-renders changed rows.[^10][^2]

## Long-Term Best Practices

- **Adopt cursor-based incremental sync as the default pull strategy.** Each table (conversations, messages) should carry an `updated_at` (and ideally `created_at`) column, and pulls should use `.gt('updated_at', cursor).order('updated_at').limit(pageSize)`, looping until a page returns fewer than `pageSize` rows — this scales independently of total history size.[^13][^6][^10]
- **Use per-conversation cursors for message sync**, not one global cursor — this lets you lazily backfill only the conversation a user opens, and keeps the "hot path" (sidebar load) decoupled from the "cold path" (full message history).[^2]
- **Implement soft deletes / tombstones.** Because a cursor query on `updated_at` cannot detect hard deletes, add a `deleted_at` column (or a small tombstones table) so deletions propagate through the same incremental pull instead of requiring full-table reconciliation.[^6]
- **Push writes optimistically, local-first.** New messages/conversations should write to Dexie immediately (with a `syncStatus: 'pending'|'synced'` flag), update the UI via the reactive store, and be pushed to Supabase asynchronously with retry/backoff — mirroring the "write locally, sync in background" pattern used across Dexie-based offline-first apps [^2][^9][^14].
- **Consider event-sourcing/append-only design for messages.** Since messages are typically immutable once sent, treating the messages table as append-only (with edits/deletes as new events) simplifies incremental sync because you never need to diff mutated rows, only append new ones.[^2]
- **Evaluate CRDTs (Loro, Automerge, Yjs) only if you need true concurrent multi-device conflict resolution** (e.g., simultaneous edits to the same message from two devices) — for a chat app where messages are largely append-only, last-write-wins on `updated_at` is usually sufficient and far simpler to reason about.[^11][^7]
- **Consider Dexie Cloud** if you want much of this sync machinery (queued mutations, WebSocket/long-polling sync, conflict resolution) provided out-of-the-box rather than hand-rolled against Supabase.[^15][^8]

## Supabase Query & Schema Recommendations

- Add and index `updated_at timestamptz not null default now()` (with a trigger to bump it on every update) on both `conversations` and `messages`, and index `(user_id, updated_at)` to keep cursor queries fast.[^13][^6]
- Add `deleted_at timestamptz null` for soft deletes; filter it out in normal reads but include it in sync pulls so clients can remove local rows.[^6]
- Always pair `.select()` with an explicit `.order()` and `.range()`/`.limit()` — an unordered query relies on physical row order (`ctid`), which is unstable across `VACUUM`/`UPDATE` and can silently shift which 1,000 rows you get back.[^16][^4]
- Select only needed columns for the conversation-list sync (e.g., `id, title, updated_at, last_message_at`) rather than `select('*')`, since payload size directly affects fetch latency.[^16]
- For message pulls, paginate with keyset pagination (`.gt('id', lastId)` or `.gt('updated_at', cursor)`) rather than offset pagination — keyset pagination stays fast regardless of table depth, while offset pagination degrades as history grows.[^13][^10]
- Do not rely on raising the project's `max_rows` setting as a substitute for pagination; Supabase's own guidance is that pagination is the correct fix, and `max_rows` is a safety cap, not a sync strategy.[^17][^13]

## Race Conditions & Edge Cases

- **Concurrent local writes during an in-flight sync.** If a user sends a message while the background sync is merging remote data, ensure the merge is additive (`bulkPut` by id) rather than a destructive clear-and-replace, or the in-flight local write can be lost.[^14][^2]
- **Multi-tab / multi-device conflicts.** Two tabs (or two devices) editing the same conversation concurrently need a deterministic conflict rule — last-write-wins on `updated_at` is the simplest and is what most Dexie-based local-first apps use in practice.[^7]
- **Clock skew for `updated_at` cursors.** If timestamps are set client-side, clock drift between devices can cause a client to miss or re-fetch rows; prefer server-generated timestamps (Postgres `now()` via trigger) for the authoritative `updated_at`.[^6]
- **Sync cursor drift on hard deletes.** A pure `updated_at` cursor sync will never see hard-deleted rows, leaving orphaned local copies — this is why soft-delete tombstones are necessary, not optional, once incremental sync is adopted.[^6]
- **Partial sync failure mid-pagination.** If a paginated pull fails halfway through, persist the last successfully processed cursor so retries resume rather than restart from zero, and avoid advancing the "last synced" timestamp until the full page batch commits successfully.[^13][^6]
- **Race between "conversation list sync" and "message lazy-load".** If a user opens a conversation before its metadata sync has committed to Dexie, guard the message fetch with a check that the conversation record already exists locally (or fetch it inline) to avoid orphan message rows.[^2]

## Observability for Sync Latency

To measure and improve this over time, instrument each sync stage with timestamped, structured events rather than ad hoc logging:

- Record per-sync-run metadata: `sync_started_at`, `sync_completed_at`, `rows_pulled`, `rows_pushed`, `cursor_before`, `cursor_after`, and `duration_ms`, stored either in a local Dexie `sync_log` table or sent to your analytics/telemetry backend.
- Track **time-to-first-render** (Dexie read → UI paint) separately from **time-to-fresh** (background reconciliation complete) — these are the two latency numbers that matter for a local-first architecture, and conflating them hides whether the "slow sidebar" complaint is actually a first-paint problem or a staleness problem.[^1][^2]
- Log Supabase response metadata (`content-range` header, row counts) to detect silent 1,000-row truncation before it causes a user-visible data-completeness bug.[^5]
- Avoid recording message content or PII in telemetry; safe fields are counts, durations, cursor values, table names, and boolean success/failure flags.

## References & Resource Links

- Supabase official docs on default row limits and pagination via `.range()`[^3][^13]
- Supabase 1,000-row cap deep dives explaining `db-max-rows` and the ordering requirement[^4][^5]
- Dexie.js official docs and Dexie Cloud Starter offline-first architecture writeup[^8][^1]
- Practical Next.js + Dexie offline-first repository-pattern case study (sync engine, `isSynced` flags, tombstones)[^2]
- Local-first Dexie app case study with UUID/tombstone/last-write-wins conflict resolution[^7]
- CRDT-based web sync engine reference implementation using Dexie + Loro CRDT[^12][^11]
- Definite.app on incremental-sync limitations around hard deletes[^6]

---

## References

1. [Offline-First Architecture | dexie/dexie-cloud-starter | DeepWiki](https://deepwiki.com/dexie/dexie-cloud-starter/6.1-offline-first-architecture) - This document explains how the Dexie Cloud Starter implements an offline-first architecture, enablin...

2. [Building an Offline-First App with Next.js, Dexie, Prisma & PWA – JB](https://jb.desishub.com/blog/offline-first-with-dexie) - A complete, production-ready guide to building web applications that work without internet. Users ca...

3. [JavaScript: Fetch data | Supabase Docs](https://supabase.com/docs/reference/javascript/v1/select) - By default, Supabase projects will return a maximum of 1,000 rows. You can use range() queries to pa...

4. [Why your Supabase query stops at exactly 1000 rows (and ...](https://dev.to/michelfaure/why-your-supabase-query-stops-at-exactly-1000-rows-and-never-tells-you-4g57) - a 1000-row Range HTTP cap applied by Supabase. The bug only exists above one thousand rows in produc...

5. [Supabase 1000 Row Limit: Silent at Post 354, Fatal at 1,000](https://picklog.cc/blog/supabase-1000-row-limit) - Supabase caps Data API responses at 1,000 rows by default. Arithmetic from a live 83-post build: sil...

6. [Supabase ETL: The Four Ways Out (and What Breaks)](https://www.definite.app/blog/supabase-etl) - incremental pulls of changed rows on a cron — keyed on a cursor column like updated_at where one exi...

7. [Building an Offline-First React App with Dexie and ...](https://algermakiputin.com/blog/offline-first-react-dexie-indexeddb/) - Offline-first means the local database is the source of truth; the network is background work. Index...

8. [Dexie.js - Offline-First Database with Cloud Sync ...](https://dexie.org/) - IndexedDB made simple. Add cloud sync for auth, storage, with real-time updates. One unified data la...

9. [Building an Offline-First Multi-Tenant SaaS with React 19 and Dexie.js](https://dev.to/imatulsrivas/building-an-offline-first-multi-tenant-saas-with-react-19-and-dexiejs-4f1k) - When I set out to build ParkManager — a multi-tenant parking management SaaS — I knew "works offline...

10. [Supabase: Handling The 1000 Row Limit - Broadwayinfosys](https://ftp.broadwayinfosys.com/blog/supabase-handling-the-1000-row-limit-1764807413) - Supabase: Handling the 1000 Row Limit What's up, everyone! So, you're working with Supabase, buildin...

11. [sync-engine-web/README.md at main · typeonce-dev/sync-engine-web](https://github.com/typeonce-dev/sync-engine-web/blob/main/README.md) - A Sync Engine for the web: React (TanStack Router), Web Workers, Effect, Loro ⚡️ - typeonce-dev/sync...

12. [GitHub - typeonce-dev/sync-engine-web: A Sync Engine for the web: React (TanStack Router), Web Workers, Effect, Loro ⚡️](https://github.com/typeonce-dev/sync-engine-web) - A Sync Engine for the web: React (TanStack Router), Web Workers, Effect, Loro ⚡️ - typeonce-dev/sync...

13. [Paginate Results in Supabase | Tutorial | RapidDev](https://www.rapidevelopers.com/supabase-tutorial/how-to-paginate-results-in-supabase) - Implement offset pagination with .range() and keyset pagination for large tables. Build page navigat...

14. [Builing an offline-first app with build-from-scratch Sync ...](https://dev.to/daliskafroyan/builing-an-offline-first-app-with-build-from-scratch-sync-engine-4a5e) - IndexedDB would provide reliable local storage, Dexie.js would make it pleasant to work with, and I ...

15. [Building Local-First Apps with Vue and Dexie.js](https://alexop.dev/posts/building-local-first-apps-vue-dexie/) - Dexie.js provides a robust offline-first architecture where database operations run against local In...

16. [select('*') without .limit() in Supabase — unbounded queries](https://lumioguard.dev/checks/select-without-limit) - A supabase-js select with no limit returns every matching row until the day it cannot. How Max Rows ...

17. [Supabase data fetching (over 1000 items) - How do I?](https://community.weweb.io/t/supabase-data-fetching-over-1000-items/20174) - Hi, I found out that I can overcome the Supabase rows limitation directly in the Supabase settings (...

