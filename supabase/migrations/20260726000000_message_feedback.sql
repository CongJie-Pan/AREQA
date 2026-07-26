alter table public.messages
  add column if not exists feedback text;

alter table public.messages
  add column if not exists feedback_updated_at timestamptz;

alter table public.messages
  drop constraint if exists messages_feedback_valid;

alter table public.messages
  add constraint messages_feedback_valid
  check (
    feedback is null
    or (role = 'assistant' and feedback in ('liked', 'disliked'))
  );
