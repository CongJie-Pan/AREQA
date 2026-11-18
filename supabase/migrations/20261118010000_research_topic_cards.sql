-- Topic Finder (選題) topic cards: derived, server-only state per conversation.
-- The AI only writes `pending`; stage/version change when the learner confirms.
create table if not exists public.research_topic_cards (
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  stage smallint not null default 0 check (stage between 0 and 6),
  version integer not null default 0 check (version >= 0),
  card jsonb not null default '{}'::jsonb check (octet_length(card::text) <= 32768),
  pending jsonb check (pending is null or octet_length(pending::text) <= 32768),
  history jsonb not null default '[]'::jsonb check (octet_length(history::text) <= 65536),
  updated_at bigint not null,
  primary key (user_id, conversation_id)
);

alter table public.research_topic_cards enable row level security;
revoke all on public.research_topic_cards from anon, authenticated;
grant select, insert, update, delete on public.research_topic_cards to service_role;
-- No browser policies: the backend reads and writes cards; the client uses its API.
