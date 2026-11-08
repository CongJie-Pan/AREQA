# Long conversation context

Chat history remains in the existing browser/cloud persistence flow. Requests
continue carrying the full conversation because cloud sync is asynchronous; a
conversation ID alone cannot yet guarantee that the server has the latest turn.
The transport allows 10,000 messages and 4 MiB of serialized UTF-8 history. These
are transport protections, not a model context window or a permanent chat cap.

`services/conversation/history.py` runs at the final answer provider boundary,
after system/memory/RAG instructions and tool schemas have been assembled. Small
prompts are unchanged. Oversized prompts retain system instructions and complete
recent user turns, summarize older messages in bounded batches, and add up to
three matching original messages using lexical English/CJK overlap. Recall only
searches the supplied transcript; it is not semantic cross-conversation memory.

Configuration (backend environment, case-insensitive Pydantic settings):

| Setting | Default | Meaning |
| --- | --- | --- |
| `MODEL_CONVERSATION_SUMMARY` | `google/gemini-3.1-flash-lite` | Independent summary model; main answer and GUM models are unchanged |
| `CONVERSATION_CONTEXT_TOKENS` | 32768 | Conservative total allowance; set at or below the selected model's supported context |
| `CONVERSATION_SUMMARY_TOKENS` | 1536 | Maximum generated summary tokens |
| `CONVERSATION_SUMMARY_TIMEOUT_SECONDS` | 20 | Total timeout for incremental updates |
| `CONVERSATION_SUMMARY_COLD_TIMEOUT_SECONDS` | 45 | Total timeout when no compatible checkpoint exists |
| `CONVERSATION_SUMMARY_CONTEXT_TOKENS` | 524288 | Independent conservative summary allowance; configure at or below the summary model context |
| `DATABASE_URL` | unset | Server-only PostgreSQL connection for durable checkpoints |
| `ENABLE_CONVERSATION_COMPACTION` | true | If false, oversized prompts are rejected rather than sent unbounded |

Token estimates intentionally use serialized UTF-8 bytes plus framing as a
conservative text proxy. The budget reserves completion tokens, tool schemas and
1024 units of safety margin. Native PDF/image expansion is provider-dependent;
this estimator cannot guarantee the expanded multimodal token count. Tool and
attachment provider limits continue to apply.

Summary keys include user, conversation, model, summary-instruction hash and a
SHA-256 transcript prefix digest. Old-message edits, prompt changes and forks
cannot reuse incompatible summaries. In-process entries are bounded to 128 and
expire after 30 minutes. An optional PostgreSQL checkpoint store allows restarts
and other workers to reuse the longest matching prefix. It verifies conversation
ownership and stores up to 16 recent versions per conversation across models and
prompt versions. Checkpoints older than 30 days are ignored; expired versions are
removed when that conversation next saves a checkpoint. Conversation/account
foreign keys cascade deletion. Source transcripts remain unchanged.

Cold starts batch as much older history as fits the **summary** model allowance,
rather than repeatedly using half the smaller **answer** budget. Histories larger
than that allowance still use multiple bounded requests. Subsequent turns merge
only newly aged messages into the compatible previous summary. This reduces
serial model calls; it does not guarantee summary fidelity or real-provider latency.
Native image/file expansion is still subject to provider limits.

Summary failures/timeouts retain valid prior coverage and bounded recent context,
optionally recalling relevant originals. They **never prepend a history-degradation
warning to the answer**. The separate notice for missing retrieval evidence remains.
Waiting more than one second emits an SSE `status` event; subsequent heartbeats
keep the connection active. These events do not enter the saved answer. Disconnect
or cancellation cancels the in-flight preparation task. Oversized mandatory
instructions/current turns still receive a readable capacity error, without
silently cutting current input. Empty/truncated summaries are never cached.

### Database rollout

Apply `supabase/migrations/20261108000000_conversation_summary_checkpoints.sql`
through the existing database migration process before enabling persistent reuse.
The backend `DATABASE_URL` role needs access; browser `anon`/`authenticated` roles
have no table privileges or RLS policies. The migration grants `service_role`
access. No existing transcript backfill is required: the next oversized request
creates a checkpoint after a successful summary.

A missing database/configuration/schema or database failure fails soft to the
process cache. Database operations are capped at two seconds and failures open a
60-second retry circuit. Unsaved conversations cannot create durable checkpoints
until cloud persistence has created the owner-matching conversation row.

Safe terminal events include `history.compaction_started` (cache source, covered
and total messages, summary budget, timeout), `history.summary_started/completed`
(provider counts, usage and elapsed time), `history.checkpoint_saved/skipped`,
`history.checkpoint_unavailable` (operation/error type only),
`history.summary_failed` (reason/covered/total), and `history.prepared`
(cache source, coverage and degraded flag). No transcript, summary, prompt,
credentials or arbitrary provider/database exception text is logged.

## Validation

```sh
backend/.venv/bin/python -m pytest tests/backend/test_conversation_history.py tests/backend/test_conversation_history_stream.py tests/backend/test_history_transport.py tests/backend/test_summary_store.py tests/backend/test_retrieval_budget.py -q
npm test --prefix frontend -- tests/frontend/utils/validation.test.ts tests/frontend/api/chat/route.attachments.test.ts
npm run check:report:strict
```

Before production rollout, run a real-provider browser conversation beyond 100
messages, trigger multiple summary updates, edit an early constraint, and ask for
an old detail. Check answer fidelity, cost and latency. Repeat with native PDF and
image inputs. Mocked tests prove budget/control-flow contracts, not model summary
accuracy. ID-only transport still requires a reliable server history synchronization contract;
checkpoint reuse continues validating the transcript supplied by the browser.

The generic summary instruction merges earlier state with new messages and preserves
still-applicable user decisions/constraints unless explicitly superseded or clearly
out of scope. Repetition and explanatory prose are removed before active constraints;
uncertain applicability stays labelled by topic. The 450-word instruction and default
1536-token output limit are unchanged. This prompt revision was checked with focused
backend tests only; the PDF/model comparison was not rerun at the user's request.

## Retrieval context budget regression

A short question plus large web/RAG results previously failed before compaction:
retrieval was prepended to the last user message and the entire augmented message
was treated as mandatory. The observed five-message request with twelve search
results is now covered by `tests/backend/test_retrieval_budget.py`.

The execution/mixin/stream chain passes the exact request-scoped server retrieval
prefix to `prepare_history`. `context_budget.py` separates only that known prefix;
it never guesses from user-authored `<context>` tags. The existing assembly
contract remains intact. All budget processing happens on copied provider inputs,
including the actual system overlays, tools, output reserve and attachments.

If the assembled prompt fits, retrieval is unchanged. Otherwise retrieval gets
at most one third of the input allowance and no more than the space left after
mandatory instructions and current user content. Excerpts are shortened with
Unicode-safe boundaries while retaining source labels and URL headers. Headers
that cannot fit are omitted; remaining sources keep their original citation IDs.
The UI source inventory is unchanged, and only retained excerpts reach the model.
An all-omitted result gets an explicit unavailable-evidence marker and visible
notice; if even that marker cannot fit, the request is rejected safely. Long
history can still be compacted after retrieval is bounded.

`retrieval.context_budgeted` logs correlation ID, input allowance, mandatory sizes,
original/selected retrieval sizes, source counts and trimming state. `history.rejected`
now preserves the actual safe reason code and logs budget/system/current-turn/
retrieval/tool sizes and completion reservation. These are serialized UTF-8 proxy
sizes, not provider-native token measurements. Neither event logs source titles,
URLs, excerpts, user text or credentials.

Regression validation:

```sh
backend/.venv/bin/python -m pytest tests/backend/test_retrieval_budget.py tests/backend/test_conversation_history.py tests/backend/test_conversation_history_stream.py tests/backend/test_history_transport.py tests/backend/test_orchestration_service.py tests/backend/test_conversation_context_service.py -q
npm run check:report:strict
```

Coverage includes real source formatting and prompt constants, web/RAG grounding,
multimodal attachment preservation, the actual execution-to-stream handoff, budget
accounting with provider tool schemas, long-history compaction, source omission,
unavailable evidence and precise rejection diagnostics. Model/search I/O and
memory persistence are mocked; no PDF replay or paid provider calls are required.

The combined regression gate for this change passed **119 tests**, with **3 skips**:
one existing PDF visual test requires optional `fitz`/PyMuPDF, and two existing
router tests are explicitly disabled. `npm run check:report:strict` also passed.
The five-message/twelve-source regression was observed failing with
`current_turn_too_large` before the fix, then passing afterward. Production
browser/provider replay was not performed; the supplied screenshot/logs remain
private local evidence rather than committed fixtures.

## Cold-start regression validation (2026-11-08)

Before the fix, a synthetic 110-message history required 54 summary calls under
a small answer budget, and a timeout inserted the unwanted warning. Both
regressions were observed failing, then passing after the change: one summary
request now covers that fixture, and timeouts stream normal answers without the
history warning. Tests cover incremental updates, partial-timeout reuse, changed
sources/models/prompts, separate waiting status, cancellation, and safe logs.

Durable integration tests execute the store SQL against a temporary SQLite file
and reopen it with a fresh engine after clearing process state. They cover restart
reuse, ownership, upserts, expiry and version limits. These do not validate
PostgreSQL privileges, RLS, or production connectivity; the production migration
and a browser/provider replay remain rollout checks. No private transcript or PDF
was replayed, and no live migration was applied in this implementation session.

The final scoped backend gate passed **135 tests**, with **3 existing skips**
(one optional PDF visual dependency and two explicitly disabled router tests).
ESLint and TypeScript strict checks passed.
