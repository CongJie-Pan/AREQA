create table if not exists public.conversation_shares (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null,
  owner_user_id uuid not null,
  share_token text not null unique,
  is_public boolean not null default true,
  created_at timestamptz not null default timezone('utc'::text, now()),
  updated_at timestamptz not null default timezone('utc'::text, now()),
  revoked_at timestamptz
);

create unique index if not exists conversation_shares_conversation_id_key
  on public.conversation_shares(conversation_id);

create index if not exists idx_conversation_shares_public_token
  on public.conversation_shares(share_token)
  where is_public = true and revoked_at is null;

alter table public.conversation_shares enable row level security;

grant select, insert, update, delete on public.conversation_shares to authenticated;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'conversation_shares'
      and policyname = 'conversation_shares_owner_select'
  ) then
    create policy conversation_shares_owner_select
      on public.conversation_shares
      for select
      to authenticated
      using (owner_user_id = (select auth.uid()));
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'conversation_shares'
      and policyname = 'conversation_shares_owner_insert'
  ) then
    create policy conversation_shares_owner_insert
      on public.conversation_shares
      for insert
      to authenticated
      with check (
        owner_user_id = (select auth.uid())
        and exists (
          select 1
          from public.conversations c
          where c.id = conversation_id
            and c.user_id = (select auth.uid())
        )
      );
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'conversation_shares'
      and policyname = 'conversation_shares_owner_update'
  ) then
    create policy conversation_shares_owner_update
      on public.conversation_shares
      for update
      to authenticated
      using (owner_user_id = (select auth.uid()))
      with check (
        owner_user_id = (select auth.uid())
        and exists (
          select 1
          from public.conversations c
          where c.id = conversation_id
            and c.user_id = (select auth.uid())
        )
      );
  end if;

  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'conversation_shares'
      and policyname = 'conversation_shares_owner_delete'
  ) then
    create policy conversation_shares_owner_delete
      on public.conversation_shares
      for delete
      to authenticated
      using (owner_user_id = (select auth.uid()));
  end if;
end $$;

create or replace function public.get_public_conversation_share(p_share_token text)
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select jsonb_build_object(
    'id', c.id,
    'title', c.title,
    'createdAt', c.created_at,
    'updatedAt', c.updated_at,
    'messages', coalesce(
      jsonb_agg(
        jsonb_build_object(
          'id', m.id,
          'role', m.role,
          'content', m.content,
          'citations', m.citations,
          'sources', m.sources,
          'answerBlocks', m.answer_blocks,
          'createdAt', m.created_at
        )
        order by m.created_at asc
      ) filter (where m.id is not null),
      '[]'::jsonb
    )
  )
  from public.conversation_shares s
  join public.conversations c
    on c.id = s.conversation_id
  left join public.messages m
    on m.conversation_id = c.id
   and m.user_id = s.owner_user_id
  where s.share_token = p_share_token
    and s.is_public = true
    and s.revoked_at is null
  group by c.id, c.title, c.created_at, c.updated_at;
$$;

revoke all on function public.get_public_conversation_share(text) from public;
grant execute on function public.get_public_conversation_share(text) to anon, authenticated;
