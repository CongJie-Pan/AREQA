-- Track message edit recency so cloud pulls can avoid overwriting newer local edits.
alter table public.messages
  add column if not exists updated_at timestamptz;

update public.messages
set updated_at = coalesce(created_at, timezone('utc'::text, now()))
where updated_at is null;

alter table public.messages
  alter column updated_at set default timezone('utc'::text, now()),
  alter column updated_at set not null;

create index if not exists idx_messages_user_updated_at
  on public.messages(user_id, updated_at desc);
