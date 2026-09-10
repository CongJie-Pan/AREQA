-- Add synchronized organization metadata for saved notes.
alter table public.notes
  add column if not exists tags text[] not null default '{}',
  add column if not exists is_pinned boolean not null default false;

create index if not exists idx_notes_user_pinned_created_at
  on public.notes(user_id, is_pinned desc, created_at desc);

create index if not exists idx_notes_user_tags
  on public.notes using gin (tags);
