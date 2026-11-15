-- Remember that the learner pressed Stop on an assistant reply, so the
-- "you stopped AREQA's response" notice survives reloads and other devices.
alter table public.messages
  add column if not exists stopped_by_user boolean not null default false;
