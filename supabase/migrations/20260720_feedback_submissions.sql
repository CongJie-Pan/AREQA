create table if not exists public.feedback_submissions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  email text,
  display_name text,
  content text not null,
  page_path text,
  user_agent text,
  status text not null default 'new',
  created_at timestamptz not null default now(),
  constraint feedback_submissions_content_not_blank check (length(btrim(content)) > 0),
  constraint feedback_submissions_content_max_length check (char_length(content) <= 2000)
);

create index if not exists idx_feedback_submissions_created_at
  on public.feedback_submissions(created_at desc);

create index if not exists idx_feedback_submissions_user_id
  on public.feedback_submissions(user_id);

alter table public.feedback_submissions enable row level security;

grant insert on public.feedback_submissions to authenticated;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'feedback_submissions'
      and policyname = 'feedback_submissions_insert_own_user'
  ) then
    create policy feedback_submissions_insert_own_user
      on public.feedback_submissions
      for insert
      with check (user_id = auth.uid());
  end if;
end $$;
