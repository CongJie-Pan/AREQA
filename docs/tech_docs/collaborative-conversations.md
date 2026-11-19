# Collaborative conversations

Phase 1 and 2 of shared conversations that other signed-in users can join and
use to ask the AI together.

## Behavior

- The share panel offers **View only** (unchanged read-only snapshot) or
  **Can participate**.
- A signed-in visitor of a participate link sees **Join shared chat** on the
  share page. Joining adds them to `conversation_members` and opens
  `/collab/<conversationId>`.
- Signed-out visitors see the snapshot and are asked to sign in first.
- On `/collab/<id>` the owner and participants see the whole conversation, who
  asked each question, and can ask the AI. Other people's messages appear
  within about 5 seconds (polling). Realtime sync is phase 4.
- The owner can remove participants in the share panel. Switching the link
  back to view-only removes every participant's access immediately.

## Boundaries

| Concern | Owner |
| --- | --- |
| Who may read/write | Postgres security definer functions in `supabase/migrations/20261119000000_collaborative_conversations.sql`, called with the caller's JWT |
| Message ownership | `messages.user_id` is always the conversation owner, so the owner's existing sync receives participant messages; `messages.author_user_id` is the real author (null = owner) |
| AI history | FastAPI `/api/v1/stream` asks `get_collaborative_context` and replaces the client history with the stored one (`backend/services/conversation/collaboration.py`) |
| Personal memory | Always off for collaborative turns (`isolated_context=True`), for the owner too. If the lookup fails the turn still runs, with memory off |
| Spend | Each turn counts against the asker's existing limits, plus 20 AI replies per 5 minutes per shared conversation (in-process) |

No service key is involved. Next.js routes under `/api/collab/*` only validate
input and forward to the database functions. Only display names leave
`auth.users`; emails are never returned to other participants.

## Rollout

1. Apply the migration in Supabase.
2. Deploy the backend and frontend together. Before the migration is applied,
   participate links return 503 and every existing path works as before.

## Known limits (later phases)

- No generation lock yet: two people asking at once both get replies (phase 3).
- The asker's browser stores the AI reply; if it closes mid-reply, the reply
  is lost for the others.
- The owner's normal chat view shows participant questions without author
  labels until the next sync; `/collab/<id>` shows authors.
- Collaborative pages do not support attachments, voice, or Topic Finder mode.
- Every signed-in chat turn now makes one extra Supabase RPC
  (`collaboration.lookup_resolved ... elapsed_ms=` in logs) so a cache may be
  worth adding if that shows up in latency traces.
