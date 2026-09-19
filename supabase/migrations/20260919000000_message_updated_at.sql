-- Track message edit recency so cloud pulls can avoid overwriting newer local edits.
alter table public.messages
  add column if not exists updated_at timestamptz not null default timezone('utc'::text, now());

update public.messages
set updated_at = coalesce(updated_at, created_at, timezone('utc'::text, now()));

create index if not exists idx_messages_user_updated_at
  on public.messages(user_id, updated_at desc);
