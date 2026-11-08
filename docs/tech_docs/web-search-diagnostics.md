# Web search UI-to-server diagnostics

Engineers do not automatically see a user's screen. These events record reported
UI state and request/response metadata to reconstruct search behavior. They do not
capture screenshots, session video, message text, source content, URLs, passwords,
API keys or tokens. Receiving sources is not proof that the browser painted them.

## Enable and reproduce

Deploy both frontend and backend changes. The existing backend setting
`ENABLE_CONVERSATION_HISTORY_DEBUG_LOGS` controls the frontend's
`conversationHistoryDebugLogs` runtime flag. If disabled, the new browser debug
bridge sends nothing. Server request/decision logs still report routing metadata.

1. Click the globe button to enable web search.
2. Send a text question and note the approximate time and conversation.
3. Capture backend terminal logs around that time, including the events below.
4. Match stream/request/decision events by `requestId` / `request_id` and use
   `run_id` to join turn-trace events. Existing provider logs can be compared by
   conversation and time.

Browser debug posts use the existing `/api/v1/conversation-history/debug-log`
endpoint. They are best-effort, unawaited, and aborted after three seconds. A
missing browser debug event can mean disabled logging or failed delivery; it does
not prove the user did not click. `clientTimestampMs` records browser event time,
which can differ from server time. UI events can arrive out of order.

## Events and interpretation

| Event | Observes |
| --- | --- |
| `chat_history_search_toggle` | Previous and resulting search mode, Web Search/RAG state, active conversation |
| `chat_history_search_send_clicked` | Search settings and attachment count at the send action |
| `chat_history_search_stream_request` | Actual payload mode/flags and current UI mode/flag, plus request ID |
| `stream.request_accepted` | Backend-received mode, legacy web flag, RAG flag, request ID and message/upload counts |
| `orchestration.search_decision` | Effective mode, selected search action/reason, request ID, run ID and conversation ID |
| `chat_history_search_sources_received` | Number of sources received by the browser parser, plus request ID |

The first two UI events are associated by conversation/time; a newly created
conversation may not yet have an ID. The request ID is generated at stream
creation and forwarded through the Next.js proxy's `X-Request-ID` header. Only
bounded identifier characters are forwarded/logged. No authentication header is
copied into diagnostic bodies. The backend independently allowlists diagnostic
fields and validates search-mode enums, booleans, counts and request IDs.

Useful comparisons:

- UI mode `always`, payload mode `never`: inspect call-site overrides or state
  capture timing. This mismatch is evidence of differing state, not proof of a
  particular frontend bug.
- Payload `always`, backend `never` with the same request ID: inspect forwarding
  and version consistency.
- Backend raw mode `auto`, effective mode `never`: check automatic-search settings.
- Decision `should_search=True`, no search completion: inspect existing provider,
  timeout, refusal and execution events for the same run.
- Provider completes but browser receives no sources: inspect valid-source
  filtering and SSE transport/parser events.
- Browser receives sources but user sees none: inspect callback/store/rendering;
  obtain a screenshot or reproduce the UI. No screen recording is enabled here.

`search_mode` takes precedence over legacy `use_web_search`; contradictory values
are deliberately logged separately. In the supplied latest logs the five later
turns did not invoke web search. Those old logs do not include the raw routing
parameters, so their precise UI/input cause remains unverified. No search-routing
behavior is changed by this observability update.

## Validation

Focused frontend coverage checks button/send diagnostics, UI-versus-payload
state, source counts, header correlation, field filtering, feature gating and
network failure/timeout isolation. The ChatInput test harness explicitly supplies
the expected language rather than depending on the product's English default.
Backend tests exercise HTTP logging/sanitization and real search policy decisions
with no model calls. Production browser reproduction remains required.

Validation result: 114 focused frontend tests passed; 127 backend tests passed
with 3 existing/optional-dependency skips. Frontend strict ESLint/TypeScript checks
passed. No live user session or paid model request was used for these checks.
