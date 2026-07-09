-- AREQA cold-memory schema for Supabase PostgreSQL.
--
-- Purpose:
--   This migration creates the long-term memory tables used by GUM / cold memory:
--   - observations
--   - propositions
--   - observation_proposition
--   - vec_memory
--   It also enables the vector extension, adds indexes, and applies RLS policies.
--
-- Why this file exists:
--   Hot memory lives in Redis, but cold memory is stored in Supabase/PostgreSQL.
--   Keeping this schema in version control makes the database reproducible and
--   prevents cloud schema drift.
--
-- When to use it:
--   Apply this migration to a fresh or partially-provisioned Supabase project
--   before running cold-memory, GUM, or vector search tests.

create extension if not exists vector;

create table if not exists public.observations (
  id bigserial primary key,
  observer_name varchar(100) not null,
  content text not null,
  content_type varchar(50) not null,
  status varchar(50) not null default 'active',
  user_id varchar(50) not null default 'default_user',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.propositions (
  id bigserial primary key,
  text text not null,
  reasoning text not null,
  context_scope varchar(255),
  event_types text,
  target varchar(255),
  functional_type_seeds text,
  confidence integer,
  decay integer,
  status varchar(50) not null default 'active',
  user_id varchar(50) not null default 'default_user',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  revision_group varchar(36) not null,
  version integer not null default 1
);

create table if not exists public.observation_proposition (
  observation_id bigint not null references public.observations(id) on delete cascade,
  proposition_id bigint not null references public.propositions(id) on delete cascade,
  primary key (observation_id, proposition_id)
);

create table if not exists public.vec_memory (
  id bigint primary key references public.propositions(id) on delete cascade,
  embedding vector not null,
  updated_at timestamptz not null default now()
);

create index if not exists idx_observations_user_id on public.observations(user_id);
create index if not exists idx_observations_status on public.observations(status);
create index if not exists idx_observations_created_at on public.observations(created_at desc);
create index if not exists idx_propositions_user_id on public.propositions(user_id);
create index if not exists idx_propositions_status on public.propositions(status);
create index if not exists idx_propositions_created_at on public.propositions(created_at desc);
create index if not exists idx_propositions_revision_group on public.propositions(revision_group);
create index if not exists idx_propositions_text_fts on public.propositions using gin (to_tsvector('english', text));
create index if not exists idx_observations_content_fts on public.observations using gin (to_tsvector('english', content));

alter table public.observations enable row level security;
alter table public.propositions enable row level security;
alter table public.observation_proposition enable row level security;
alter table public.vec_memory enable row level security;

grant usage on schema public to authenticated;
grant select, insert, update, delete on public.observations to authenticated;
grant select, insert, update, delete on public.propositions to authenticated;
grant select, insert, update, delete on public.observation_proposition to authenticated;
grant select, insert, update, delete on public.vec_memory to authenticated;
grant usage, select on sequence public.observations_id_seq to authenticated;
grant usage, select on sequence public.propositions_id_seq to authenticated;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'observations' and policyname = 'observations_user_isolation'
  ) then
    create policy observations_user_isolation
      on public.observations
      for all
      to authenticated
      using (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'))
      with check (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'));
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'propositions' and policyname = 'propositions_user_isolation'
  ) then
    create policy propositions_user_isolation
      on public.propositions
      for all
      to authenticated
      using (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'))
      with check (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'));
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'observation_proposition' and policyname = 'observation_proposition_user_isolation'
  ) then
    create policy observation_proposition_user_isolation
      on public.observation_proposition
      for all
      to authenticated
      using (
        exists (
          select 1
          from public.observations o
          join public.propositions p on p.id = observation_proposition.proposition_id
          where o.id = observation_proposition.observation_id
            and o.user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
            and p.user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
        )
      )
      with check (
        exists (
          select 1
          from public.observations o
          join public.propositions p on p.id = observation_proposition.proposition_id
          where o.id = observation_proposition.observation_id
            and o.user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
            and p.user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
        )
      );
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'vec_memory' and policyname = 'vec_memory_user_isolation'
  ) then
    create policy vec_memory_user_isolation
      on public.vec_memory
      for all
      to authenticated
      using (
        exists (
          select 1
          from public.propositions p
          where p.id = vec_memory.id
            and p.user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
        )
      )
      with check (
        exists (
          select 1
          from public.propositions p
          where p.id = vec_memory.id
            and p.user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
        )
      );
  end if;
end $$;
