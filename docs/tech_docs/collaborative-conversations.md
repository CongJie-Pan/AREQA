# Collaborative conversations

Phase 1 and 2 of shared conversations that other signed-in users can join and
use to ask the AI together.

## Behavior

- The share panel offers **View only** (unchanged read-only snapshot) or
  **Can participate**.
- A signed-in visitor who opens a participate link joins automatically and the
  conversation opens in the normal chat, like one of their own: it appears in
  the sidebar and uses the usual composer. If joining fails, the read-only copy
  is shown instead.
- Signed-out visitors see the snapshot and are asked to sign in first.
- While a shared conversation is open (owner or participant), it refreshes
  about every 5 seconds when no answer is streaming. Realtime sync is phase 4.
- The owner can remove participants in the share panel. Switching the link
  back to view-only removes every participant's access immediately; their
  local copy disappears on the next sync.
- A participant deleting the conversation from the sidebar leaves it.

## Local-first sync

A participant's copy is a local conversation with
`collaboration: { role: 'editor', ownerUserId }`. `syncService` routes it
through `frontend/src/services/collaborationSync.ts` instead of the owner-only
tables:

| Local action | Participant copy |
| --- | --- |
| Pull messages | `get_collaborative_conversation`, merged by the existing reconciliation |
| Push message (repeated while streaming) | `append_collaborative_message` upsert; only the author may update |
| Push conversation | skipped (the row belongs to the owner) |
| Delete message (edit/regenerate) | `delete_own_collaborative_message`; others' messages stay |
| Feedback | local only |
| Delete conversation | leave (`conversation_members` row) |
| Full pull | `list_my_collaborative_conversations` adds, refreshes and drops copies |

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

1. Apply both migrations in Supabase
   (`20261119000000_collaborative_conversations.sql`, then
   `20261119010000_collaborative_conversations_in_app.sql`).
2. Deploy the backend and frontend together. Before the migration is applied,
   participate links return 503 and every existing path works as before.

## Known limits (later phases)

- No generation lock yet: two people asking at once both get replies (phase 3).
- Messages do not show who asked them yet (phase 5).
- Editing or regenerating a turn someone else wrote cannot remove their
  stored messages, so the others still see the original.
- Every signed-in chat turn makes one extra Supabase RPC
  (`collaboration.lookup_resolved ... elapsed_ms=` in logs); add a cache if
  that shows up in latency traces.
