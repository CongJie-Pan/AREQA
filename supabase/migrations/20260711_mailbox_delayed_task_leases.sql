alter table public.mailbox_delayed_tasks
  add column if not exists attempt_count integer not null default 0,
  add column if not exists lease_owner text,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists last_error_code text;

create index if not exists idx_mailbox_delayed_tasks_claimable
  on public.mailbox_delayed_tasks(status, lease_expires_at, deliver_at);
