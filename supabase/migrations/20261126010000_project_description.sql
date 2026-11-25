-- Project goal from the "Create project" dialog ("您想達成什麼目標？").
-- Older clients that do not send it keep the empty default.
alter table public.projects
  add column if not exists description text not null default ''
    check (char_length(description) <= 2000);
