create table if not exists public.agent_background_jobs (
  job_id text primary key,
  idempotency_key text not null unique,
  job_type text not null,
  user_id varchar(50) not null,
  payload jsonb not null,
  payload_version integer not null default 1,
  status text not null default 'scheduled',
  attempt_count integer not null default 0,
  available_at timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  last_error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_agent_background_jobs_claimable
  on public.agent_background_jobs(status, available_at, lease_expires_at);

alter table public.agent_background_jobs enable row level security;

grant select, insert, update, delete on public.agent_background_jobs to authenticated;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'agent_background_jobs'
      and policyname = 'agent_background_jobs_user_isolation'
  ) then
    create policy agent_background_jobs_user_isolation
      on public.agent_background_jobs
      for all
      using (user_id = auth.uid()::text)
      with check (user_id = auth.uid()::text);
  end if;
end $$;
