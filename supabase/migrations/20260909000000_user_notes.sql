-- Persist user-saved notes linked to assistant responses.
create table if not exists public.notes (
  id uuid primary key,
  user_id uuid not null,
  conversation_id uuid not null,
  message_id uuid not null,
  conversation_title text,
  content_snapshot text not null,
  answer_blocks_snapshot jsonb,
  citations_snapshot jsonb,
  sources_snapshot jsonb,
  created_at timestamptz not null default timezone('utc'::text, now()),
  updated_at timestamptz not null default timezone('utc'::text, now()),
  constraint notes_has_snapshot_content check (
    char_length(btrim(content_snapshot)) > 0
    or (answer_blocks_snapshot is not null and jsonb_array_length(answer_blocks_snapshot) > 0)
  ),
  constraint notes_answer_blocks_snapshot_is_array
    check (answer_blocks_snapshot is null or jsonb_typeof(answer_blocks_snapshot) = 'array'),
  constraint notes_citations_snapshot_is_array
    check (citations_snapshot is null or jsonb_typeof(citations_snapshot) = 'array'),
  constraint notes_sources_snapshot_is_array
    check (sources_snapshot is null or jsonb_typeof(sources_snapshot) = 'array'),
  constraint notes_user_message_unique unique (user_id, message_id),
  constraint notes_conversation_owner_fk
    foreign key (conversation_id) references public.conversations(id) on delete set null,
  constraint notes_message_fk
    foreign key (message_id) references public.messages(id) on delete set null
);

alter table public.notes
  alter column conversation_id drop not null,
  alter column message_id drop not null;

create index if not exists idx_notes_user_created_at
  on public.notes(user_id, created_at desc);

create index if not exists idx_notes_user_message
  on public.notes(user_id, message_id);

alter table public.notes enable row level security;

grant select, insert, update, delete on public.notes to authenticated;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notes'
      and policyname = 'notes_owner_select'
  ) then
    create policy notes_owner_select
      on public.notes
      for select
      to authenticated
      using (user_id = (select auth.uid()));
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notes'
      and policyname = 'notes_owner_insert'
  ) then
    create policy notes_owner_insert
      on public.notes
      for insert
      to authenticated
      with check (
        user_id = (select auth.uid())
        and (
          conversation_id is null
          or exists (
            select 1
            from public.conversations c
            where c.id = conversation_id
              and c.user_id = (select auth.uid())
          )
        )
        and (
          message_id is null
          or exists (
            select 1
            from public.messages m
            where m.id = message_id
              and m.user_id = (select auth.uid())
              and m.role = 'assistant'
          )
        )
      );
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notes'
      and policyname = 'notes_owner_update'
  ) then
    create policy notes_owner_update
      on public.notes
      for update
      to authenticated
      using (user_id = (select auth.uid()))
      with check (user_id = (select auth.uid()));
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'notes'
      and policyname = 'notes_owner_delete'
  ) then
    create policy notes_owner_delete
      on public.notes
      for delete
      to authenticated
      using (user_id = (select auth.uid()));
  end if;
end $$;
