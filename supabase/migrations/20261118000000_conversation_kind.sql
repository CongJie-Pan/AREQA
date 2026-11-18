-- Workspace a conversation belongs to: ordinary chat or Topic Finder (選題).
-- The kind is fixed at creation; existing rows and older clients stay "chat".
alter table public.conversations
  add column if not exists kind text not null default 'chat';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'conversations_kind_check'
      and conrelid = 'public.conversations'::regclass
  ) then
    alter table public.conversations
      add constraint conversations_kind_check check (kind in ('chat', 'research_coach'));
  end if;
end $$;
