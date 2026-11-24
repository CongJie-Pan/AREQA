-- Topic Finder (選題) topic-card event log: an append-only timeline of every card
-- change (draft proposed, adopted, declined, stage set, focus set aside, review
-- set/cleared, background extraction failure) for debugging and tracing.
-- Derived, server-only debug data: each row holds a full snapshot of the stored
-- card state. Rows go away with their conversation or user (on delete cascade),
-- and the backend keeps at most the newest 500 events per conversation.
create table if not exists public.research_topic_card_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  event text not null check (event in (
    'proposed', 'adopted', 'rejected', 'stage_set', 'focus_skipped',
    'review_set', 'review_cleared', 'extraction_failed'
  )),
  source text not null check (source in ('api', 'background', 'chat')),
  stage smallint not null check (stage between 1 and 6),
  version integer not null check (version >= 0),
  -- Focus gap kind only (for example "measure"); never learner text.
  focus_kind text check (focus_kind is null or focus_kind ~ '^[a-z_]{1,40}$'),
  state jsonb check (state is null or octet_length(state::text) <= 196608),
  created_at bigint not null
);

create index if not exists research_topic_card_events_conversation_idx
  on public.research_topic_card_events (user_id, conversation_id, id);

alter table public.research_topic_card_events enable row level security;
revoke all on public.research_topic_card_events from anon, authenticated;
grant select, insert, delete on public.research_topic_card_events to service_role;
-- No browser policies: only the backend writes and reads the log.
