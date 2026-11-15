-- Modes the learner attached to a question (e.g. Create Image, English Tutor),
-- shown as tokens inside the sent message bubble.
alter table public.messages
  add column if not exists request_modes jsonb;
