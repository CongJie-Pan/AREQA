-- Persist structured illustrated answer blocks across devices.
alter table public.messages
  add column if not exists answer_blocks jsonb;

alter table public.messages
  drop constraint if exists messages_answer_blocks_is_array;

alter table public.messages
  add constraint messages_answer_blocks_is_array
  check (answer_blocks is null or jsonb_typeof(answer_blocks) = 'array');
