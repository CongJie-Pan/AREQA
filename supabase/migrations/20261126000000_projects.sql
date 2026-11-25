-- Projects group conversations (Chat and Topic Finder) under shared
-- instructions and a project-scoped memory profile.
--
-- The browser reads and writes its own projects through RLS. The backend reads
-- a project with the caller's JWT when a turn carries `project_id`, and writes
-- the generated memory profile the same way, so ownership is always enforced
-- by these policies rather than by application code.
create table if not exists public.projects (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  instructions text not null default '' check (char_length(instructions) <= 8000),
  use_account_memory boolean not null default true,
  is_pinned boolean not null default false,
  memory_summary text check (memory_summary is null or char_length(memory_summary) <= 1000),
  memory_details jsonb not null default '[]'::jsonb check (jsonb_typeof(memory_details) = 'array'),
  memory_updated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists projects_user_updated_idx on public.projects (user_id, updated_at desc);

alter table public.projects enable row level security;

drop policy if exists "Users manage their own projects" on public.projects;
create policy "Users manage their own projects" on public.projects
  for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.projects to authenticated;

-- Deleting a project keeps its conversations; they simply leave the project.
alter table public.conversations
  add column if not exists project_id uuid references public.projects(id) on delete set null;

create index if not exists conversations_project_idx on public.conversations (project_id)
  where project_id is not null;
