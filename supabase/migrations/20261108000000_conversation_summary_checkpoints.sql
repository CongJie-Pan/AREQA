-- Derived server-only context; original messages remain authoritative.
create table if not exists public.conversation_summary_checkpoints (
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  model text not null,
  prompt_hash text not null,
  source_hash text not null,
  covered integer not null check (covered > 0),
  summary text not null check (octet_length(summary) <= 65536),
  updated_at bigint not null,
  primary key (user_id, conversation_id, model, prompt_hash, source_hash)
);

alter table public.conversation_summary_checkpoints enable row level security;
revoke all on public.conversation_summary_checkpoints from anon, authenticated;
grant select, insert, update, delete on public.conversation_summary_checkpoints to service_role;
-- No browser policies: only the trusted backend DB role may use checkpoints.
