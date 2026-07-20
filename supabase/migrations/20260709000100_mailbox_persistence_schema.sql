-- AREQA mailbox persistence schema for Supabase PostgreSQL.
--
-- Purpose:
--   Mailbox messages are user-visible data and must not depend on Redis as the
--   only copy. This migration makes Supabase/PostgreSQL the source of truth for
--   mailbox messages and delayed delivery metadata.
--
-- Runtime model:
--   - mailbox_messages stores delivered/user-visible mail.
--   - mailbox_delayed_tasks stores scheduled mail tasks so workers can rebuild
--     Redis delayed queues after Redis flushes, backend restarts, or redeploys.
--   - Redis remains a cache, queue, lock, and dedupe helper.

create table if not exists public.mailbox_messages (
  mail_id text primary key,
  user_id varchar(50) not null,
  sender varchar(255) not null,
  subject text not null default '',
  recipient varchar(255) not null default 'User',
  content text not null,
  conversation_id text,
  delivered_task_id text unique,
  status varchar(50) not null default 'delivered',
  is_read boolean not null default false,
  created_at timestamptz not null default now(),
  delivered_at timestamptz,
  read_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.mailbox_delayed_tasks (
  task_id text primary key,
  user_id varchar(50) not null,
  payload jsonb not null,
  status varchar(50) not null default 'scheduled',
  deliver_at timestamptz not null,
  delivered_mail_id text references public.mailbox_messages(mail_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_mailbox_messages_user_created
  on public.mailbox_messages(user_id, created_at desc);
create index if not exists idx_mailbox_messages_user_unread
  on public.mailbox_messages(user_id, is_read)
  where recipient = 'User';
create index if not exists idx_mailbox_delayed_tasks_status_due
  on public.mailbox_delayed_tasks(status, deliver_at);
create index if not exists idx_mailbox_delayed_tasks_user_status
  on public.mailbox_delayed_tasks(user_id, status);

alter table public.mailbox_messages enable row level security;
alter table public.mailbox_delayed_tasks enable row level security;

grant select, insert, update, delete on public.mailbox_messages to authenticated;
grant select, insert, update, delete on public.mailbox_delayed_tasks to authenticated;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'mailbox_messages' and policyname = 'mailbox_messages_user_isolation'
  ) then
    create policy mailbox_messages_user_isolation
      on public.mailbox_messages
      for all
      to authenticated
      using (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'))
      with check (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'));
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'mailbox_delayed_tasks' and policyname = 'mailbox_delayed_tasks_user_isolation'
  ) then
    create policy mailbox_delayed_tasks_user_isolation
      on public.mailbox_delayed_tasks
      for all
      to authenticated
      using (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'))
      with check (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub'));
  end if;
end $$;
