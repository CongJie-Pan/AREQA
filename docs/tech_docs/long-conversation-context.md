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
| `CONVERSATION_CONTEXT_TOKENS` | 32768 | Conversation text token allowance including tool/output reservations (about 85 KB of chat text) |
| `CONVERSATION_ATTACHMENT_TOKENS` | 131072 | Separate estimated attachment reading allowance |
| `CONVERSATION_PROVIDER_CONTEXT_TOKENS` | 262144 | Combined provider allowance; configure at or below the selected answer model context |
| `CONVERSATION_SUMMARY_TOKENS` | 1536 | Maximum generated summary tokens |
| `CONVERSATION_SUMMARY_TIMEOUT_SECONDS` | 20 | Total timeout for incremental updates |
| `CONVERSATION_SUMMARY_COLD_TIMEOUT_SECONDS` | 45 | Total timeout when no compatible checkpoint exists |
| `CONVERSATION_SUMMARY_CONTEXT_TOKENS` | 524288 | Independent conservative summary allowance; configure at or below the summary model context |
| `DATABASE_URL` | unset | Server-only PostgreSQL connection for durable checkpoints |
| `ENABLE_CONVERSATION_COMPACTION` | true | If false, oversized prompts are rejected rather than sent unbounded |

Conversation text estimates use serialized UTF-8 bytes plus framing as a
conservative text proxy, excluding native file/image payloads and server-marked
uploaded text parts. The token allowance minus completion tokens and a 1024-token
safety margin is converted to bytes at 3 bytes per token (about one CJK character
per token; English averages about 4 bytes per token), then tool schema bytes are
subtracted. Before 2026-11-14 tokens were compared to bytes 1:1, which left about
26 KB and dropped every recent turn in long web-search conversations. Native PDF/image expansion is provider-dependent;
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

## Optional new-chat reminder

The chat UI displays a dismissible inline banner centered at the top of the chat
area after 100 AI replies, then at 105, 110, 115, and so on. User messages and
currently streaming assistant messages do not count. The banner uses normal page
flow, without a modal, backdrop, focus trap, or automatic focus change. This is a UX
recommendation, not a transport limit or a requirement to leave the conversation.
It uses the existing new-chat action and preserves the original saved chat.

Reminders wait until history handoff, text/image generation and Live Tutor activity
have finished. When reply counts jump across a threshold, only the latest due
reminder appears; earlier thresholds are not replayed. Per-account/conversation
browser-local high-water marks prevent repeats after refresh, chat switching,
edits and deletions. If localStorage is denied, deduplication lasts for the mounted
component only. Reminder preferences do not sync between devices/browsers.

The assistant-only cadence uses a separate v2 browser-storage namespace so older
total-message reminder records cannot suppress the first AI-reply reminder.

## Attachment budget correction (2026-11-09)

All uploaded PDF/image/TXT/Markdown parts are excluded from the conversation-text
allowance. A server-owned dict subtype marks uploaded text without adding any
fields to provider JSON; typed user text remains fully charged. The original
attachment payload is preserved, including during retrieval trimming.

The chat path records only attachment count and inline transport length in
`attachment.context_budget`. PDF and image reading costs are enforced by the
provider. The context budget needs no native attachment inspection subprocess,
so slow preview work or a tight container memory limit cannot cause a second
attachment parse to reject the answer. Upload validation and the native PDF
payload continue to run through their existing paths.

PDF previews render one source at a time within each request. The renderer
caps the raster's longest edge at 1,600 pixels before allocating the pixmap.

## Attachment turn latency and follow-ups (2026-11-15)

- Attachment page previews render only when the visual preflight policy allows
  visuals (explicit request, known affordance, optional or required visual
  support) or a paper walkthrough is applied. A plain "read these PDFs" turn no
  longer spends ~10 s rendering, describing and uploading images it never uses.
- PDF/TXT text extraction for upload memory runs in a worker thread so it does
  not block the event loop.
- Follow-up turns resend only attachment names. When a history user message has
  `has_upload="true"` (or a branch `attachment_source_id`), the stream route
  reloads that upload's stored text (`chat_upload_context.inherited`) so answers
  stay grounded in the document rather than its file name.
- Suggestion generation waits up to 2.5 s, and timeouts are recognised on
  Python 3.10, where `asyncio.TimeoutError` is not the builtin `TimeoutError`.

## Context audit corrections

- Optional retrieval excerpts can be removed entirely without rejecting a valid
  current question. The user receives a missing-evidence notice; source citation
  markers are filtered across streaming chunk boundaries when no excerpts remain.
- TXT/Markdown uploads keep their complete decoded text within the existing upload
  byte limits. The old 50,000-character prefix cut no longer applies. Full text is
  passed through subject to the upload and provider limits.
- Explicit provider context errors on HTTP 400/413 allow at most one smaller
  request, only before any answer or tool delta starts. The retry removes earlier
  turns and trusted retrieval, retaining instructions, current text, attachments
  and current-turn tool groups. Unrelated errors, identical requests and partial
  answers are never retried by this policy. Repeated context rejection produces
  a specific capacity response. Responses/tasks are closed or cancelled on exit.

Regression fixtures reproduce the original optional-retrieval rejection, text
tail loss and aggregate context failures. Tests cover complete uploads through
parsing and budgeting, multi-PDF admission without subprocesses, context retry
before streaming, and split citation filtering. Model calls are mocked.
Live-provider context limits still require deployment validation.

## Per-document upload context (2026-11-15)

Production showed that three uploaded papers shared one 40,000-character text
snapshot for follow-ups: the first paper used 32,718 characters, the second kept
7,280 and the third kept none. Follow-ups now use `services/attachments/document_store.py`:

- **Identity**: each PDF/TXT/Markdown upload becomes its own document (`doc_id`
  from the content hash). Extracted text is stored per document in Redis
  (`chat_upload_doc_text:*`, up to 200,000 characters each) with a manifest
  (`chat_upload_docs:*`). Original PDFs are uploaded in the background to the
  private storage bucket under `users/<hash>/chat-uploads/<upload>/<doc>.pdf`.
- **Native re-send**: when every document is a stored PDF and the total is within
  `CHAT_UPLOAD_NATIVE_FOLLOWUP_BYTES` (10 MiB), follow-ups attach the original
  PDFs again, matching the first turn's representation.
- **Text fallback**: otherwise `CHAT_UPLOAD_CONTEXT_TEXT_CHARS` (120,000) is
  water-filled across documents so short documents stay complete and none drop to
  zero. Long documents keep their opening plus the chunks that share the most
  terms with the current question.
- **Coverage note**: a server-marked text part lists each document as complete
  original PDF, complete text, partial text (kept/total characters) or
  unavailable, and tells the model not to guess from file names.
- **Fallbacks**: no manifest (older uploads) uses the legacy snapshot; Redis or
  storage failures degrade to text or legacy without failing the turn.
- **Observability**: `chat_documents.saved`, `chat_documents.originals_stored`,
  `chat_documents.loaded mode=native|text`, `chat_upload_context.inherited mode=`.
  Every answer logs `orchestration.provider_finish` with finish reason and token
  counts (prompt, completion, reasoning, cached). A `length` finish appends a
  visible notice inviting the learner to ask for continuation.
