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
| `MODEL_CONVERSATION_SUMMARY` | `google/gemini-2.5-flash-lite` | Independent summary model; main answer and GUM models are unchanged |
| `CONVERSATION_CONTEXT_TOKENS` | 32768 | Conservative total allowance; set at or below the selected model's supported context |
| `CONVERSATION_SUMMARY_TOKENS` | 1536 | Maximum generated summary tokens |
| `CONVERSATION_SUMMARY_TIMEOUT_SECONDS` | 20 | Total summary timeout per answer |
| `ENABLE_CONVERSATION_COMPACTION` | true | If false, oversized prompts are rejected rather than sent unbounded |

Token estimates intentionally use serialized UTF-8 bytes plus framing as a
conservative text proxy. The budget reserves completion tokens, tool schemas and
1024 units of safety margin. Native PDF/image expansion is provider-dependent;
this estimator cannot guarantee the expanded multimodal token count. Tool and
attachment provider limits continue to apply.

Summary cache keys include user, conversation, model and a SHA-256 transcript
prefix digest. Old-message edits and forks therefore cannot reuse incompatible
summaries. Cache entries are immutable by source prefix, bounded to 128 entries,
and expire after 30 minutes. They are process-local: restarts and multiple workers
may regenerate summaries. No durable summary migration or new long-term memory
writes are introduced. Concurrent requests may duplicate summary calls but cannot
overwrite another source version. Source transcripts are never mutated/deleted.

Summary failures/timeouts retain only valid prior coverage and bounded recent
context, optionally recalling relevant originals, and prepend a visible notice.
Oversized mandatory instructions/current turns are rejected with a readable SSE
message; current input is never silently cut. Truncated/empty summaries are not
cached. Logs contain safe counts and error types, never text or summaries.

## Validation

```sh
backend/.venv/bin/python -m pytest tests/backend/test_conversation_history.py tests/backend/test_conversation_history_stream.py tests/backend/test_history_transport.py -q
npm test --prefix frontend -- tests/frontend/utils/validation.test.ts tests/frontend/api/chat/route.attachments.test.ts
npm run check:report:strict
```

Before production rollout, run a real-provider browser conversation beyond 100
messages, trigger multiple summary updates, edit an early constraint, and ask for
an old detail. Check answer fidelity, cost and latency. Repeat with native PDF and
image inputs. Mocked tests prove budget/control-flow contracts, not model summary
accuracy. Larger-history ID-based transport and durable summaries require a
separate reliable server history synchronization contract.

Implementation-session evidence: 15 focused backend tests and 15 frontend tests
passed, including real BFF validation for 101 messages and mocked streaming wiring.
ESLint/TypeScript strict checks passed. The expanded existing
`test_conversation_context_service.py` run had 7 passes and 24 failures due to a
missing `opencc` runtime dependency in this workspace; no claim is made that this
suite or the full backend suite passed. No real-provider browser validation was
performed in this session.

Summary debug events include `history.summary_started` (model, source count, output limit),
`history.summary_completed` (elapsed time, provider input/output usage, finish reason),
and `history.prepared` (summary model, cache hit). They never include transcript or summary text.
