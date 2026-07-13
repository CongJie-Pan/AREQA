-- Persist display-only attachment metadata. File bytes and extracted content remain request-scoped.
alter table public.messages
  add column if not exists attachments jsonb not null default '[]'::jsonb;

alter table public.messages
  drop constraint if exists messages_attachments_is_array;

alter table public.messages
  add constraint messages_attachments_is_array
  check (jsonb_typeof(attachments) = 'array');
