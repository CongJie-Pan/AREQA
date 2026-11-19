-- Collaborative conversations, phase 1: edit links, members and message authors.
--
-- * A share link is either 'view' (read-only snapshot, unchanged behavior) or
--   'edit'. Signed-in visitors of an edit link can join as members.
-- * A conversation is collaborative while it has an active edit link and at
--   least one member. Switching the link back to view-only (or revoking it)
--   removes every member's access immediately; member rows stay so the owner
--   can still see and remove them.
-- * Members never touch `messages` directly. Reads and writes go through the
--   security definer functions below, which force `user_id` to the owner (so
--   the owner's existing sync picks the messages up) and `author_user_id` to
--   the caller (so attribution cannot be forged). The existing owner-only RLS
--   on `conversations` and `messages` is intentionally left unchanged.
-- * Only display names leave auth.users; member emails are never returned.

alter table public.conversation_shares
  add column if not exists access_level text not null default 'view';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'conversation_shares_access_level_check'
  ) then
    alter table public.conversation_shares
      add constraint conversation_shares_access_level_check
      check (access_level in ('view', 'edit'));
  end if;
end $$;

-- Null means the conversation owner wrote the message (all pre-existing rows).
alter table public.messages
  add column if not exists author_user_id uuid;

create table if not exists public.conversation_members (
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  user_id uuid not null,
  role text not null default 'editor' check (role in ('editor')),
  joined_via_share_id uuid references public.conversation_shares(id) on delete set null,
  created_at timestamptz not null default timezone('utc'::text, now()),
  primary key (conversation_id, user_id)
);

create index if not exists idx_conversation_members_user
  on public.conversation_members(user_id);

alter table public.conversation_members enable row level security;

-- Rows are only inserted by join_conversation_share().
grant select, delete on public.conversation_members to authenticated;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'conversation_members'
      and policyname = 'conversation_members_select'
  ) then
    create policy conversation_members_select
      on public.conversation_members
      for select
      to authenticated
      using (
        user_id = (select auth.uid())
        or exists (
          select 1 from public.conversations c
          where c.id = conversation_id and c.user_id = (select auth.uid())
        )
      );
  end if;

  -- A member may leave; the owner may remove anyone.
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'conversation_members'
      and policyname = 'conversation_members_delete'
  ) then
    create policy conversation_members_delete
      on public.conversation_members
      for delete
      to authenticated
      using (
        user_id = (select auth.uid())
        or exists (
          select 1 from public.conversations c
          where c.id = conversation_id and c.user_id = (select auth.uid())
        )
      );
  end if;
end $$;

create or replace function public.conversation_display_name(p_user_id uuid)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select nullif(btrim(coalesce(
    u.raw_user_meta_data ->> 'username',
    u.raw_user_meta_data ->> 'full_name',
    u.raw_user_meta_data ->> 'name',
    ''
  )), '')
  from auth.users u
  where u.id = p_user_id;
$$;

revoke all on function public.conversation_display_name(uuid) from public, anon, authenticated;

-- 'owner', 'editor' or null for the current caller. Editors need an active
-- edit link; owners always resolve as owner.
create or replace function public.conversation_access_role(p_conversation_id uuid)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select case
    when c.user_id = (select auth.uid()) then 'owner'
    when exists (
      select 1 from public.conversation_members m
      where m.conversation_id = c.id and m.user_id = (select auth.uid())
    ) and exists (
      select 1 from public.conversation_shares s
      where s.conversation_id = c.id
        and s.access_level = 'edit'
        and s.is_public = true
        and s.revoked_at is null
    ) then 'editor'
    else null
  end
  from public.conversations c
  where c.id = p_conversation_id;
$$;

revoke all on function public.conversation_access_role(uuid) from public, anon, authenticated;

create or replace function public.conversation_is_collaborative(p_conversation_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1 from public.conversation_shares s
    where s.conversation_id = p_conversation_id
      and s.access_level = 'edit'
      and s.is_public = true
      and s.revoked_at is null
  ) and exists (
    select 1 from public.conversation_members m
    where m.conversation_id = p_conversation_id
  );
$$;

revoke all on function public.conversation_is_collaborative(uuid) from public, anon, authenticated;

-- Public: lets the share page decide whether to offer "Join".
create or replace function public.get_conversation_share_access(p_share_token text)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select s.access_level
  from public.conversation_shares s
  where s.share_token = p_share_token
    and s.is_public = true
    and s.revoked_at is null;
$$;

revoke all on function public.get_conversation_share_access(text) from public;
grant execute on function public.get_conversation_share_access(text) to anon, authenticated;

create or replace function public.join_conversation_share(p_share_token text)
returns uuid
language plpgsql
volatile
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_share public.conversation_shares%rowtype;
begin
  if v_uid is null then
    raise exception 'authentication_required' using errcode = '42501';
  end if;

  select * into v_share
  from public.conversation_shares s
  where s.share_token = p_share_token
    and s.access_level = 'edit'
    and s.is_public = true
    and s.revoked_at is null;

  if not found then
    raise exception 'share_not_joinable' using errcode = 'P0002';
  end if;

  if v_share.owner_user_id <> v_uid then
    insert into public.conversation_members (conversation_id, user_id, joined_via_share_id)
    values (v_share.conversation_id, v_uid, v_share.id)
    on conflict (conversation_id, user_id) do nothing;
  end if;

  return v_share.conversation_id;
end;
$$;

revoke all on function public.join_conversation_share(text) from public, anon;
grant execute on function public.join_conversation_share(text) to authenticated;

-- Full conversation for the collaborative page; null when the caller has no access.
create or replace function public.get_collaborative_conversation(p_conversation_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_role text := public.conversation_access_role(p_conversation_id);
  v_result jsonb;
begin
  if v_role is null then
    return null;
  end if;

  select jsonb_build_object(
    'id', c.id,
    'title', c.title,
    'createdAt', c.created_at,
    'updatedAt', c.updated_at,
    'viewerRole', v_role,
    'viewerUserId', auth.uid(),
    'ownerUserId', c.user_id,
    'isCollaborative', public.conversation_is_collaborative(c.id),
    'messages', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'id', m.id,
          'role', m.role,
          'content', m.content,
          'citations', m.citations,
          'sources', m.sources,
          'answerBlocks', m.answer_blocks,
          'attachments', m.attachments,
          'stoppedByUser', m.stopped_by_user,
          'authorUserId', coalesce(m.author_user_id, c.user_id),
          'authorName', public.conversation_display_name(coalesce(m.author_user_id, c.user_id)),
          'createdAt', m.created_at
        )
        order by m.created_at asc
      )
      from public.messages m
      where m.conversation_id = c.id
        and m.user_id = c.user_id
    ), '[]'::jsonb)
  )
  into v_result
  from public.conversations c
  where c.id = p_conversation_id;

  return v_result;
end;
$$;

revoke all on function public.get_collaborative_conversation(uuid) from public, anon;
grant execute on function public.get_collaborative_conversation(uuid) to authenticated;

-- Backend stream context: null for personal conversations (or no access), so
-- the default path stays a single cheap lookup. Text-only history.
create or replace function public.get_collaborative_context(p_conversation_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_role text;
begin
  if not public.conversation_is_collaborative(p_conversation_id) then
    return null;
  end if;
  v_role := public.conversation_access_role(p_conversation_id);
  if v_role is null then
    return null;
  end if;

  return jsonb_build_object(
    'role', v_role,
    'messages', coalesce((
      select jsonb_agg(
        jsonb_build_object('id', m.id, 'role', m.role, 'content', m.content)
        order by m.created_at asc
      )
      from public.messages m
      join public.conversations c on c.id = m.conversation_id
      where m.conversation_id = p_conversation_id
        and m.user_id = c.user_id
        and m.role in ('user', 'assistant')
    ), '[]'::jsonb)
  );
end;
$$;

revoke all on function public.get_collaborative_context(uuid) from public, anon;
grant execute on function public.get_collaborative_context(uuid) to authenticated;

create or replace function public.append_collaborative_message(
  p_conversation_id uuid,
  p_message jsonb
)
returns uuid
language plpgsql
volatile
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_owner uuid;
  v_id uuid;
  v_role text := p_message ->> 'role';
  v_content text := p_message ->> 'content';
begin
  if v_uid is null then
    raise exception 'authentication_required' using errcode = '42501';
  end if;
  if public.conversation_access_role(p_conversation_id) is null then
    raise exception 'not_a_member' using errcode = '42501';
  end if;
  if v_role not in ('user', 'assistant') or v_content is null or length(v_content) > 200000 then
    raise exception 'invalid_message' using errcode = '22023';
  end if;

  begin
    v_id := (p_message ->> 'id')::uuid;
  exception when invalid_text_representation then
    raise exception 'invalid_message' using errcode = '22023';
  end;
  if v_id is null then
    raise exception 'invalid_message' using errcode = '22023';
  end if;

  select c.user_id into v_owner from public.conversations c where c.id = p_conversation_id;

  insert into public.messages (
    id, user_id, conversation_id, role, content,
    citations, sources, answer_blocks, suggestions,
    stopped_by_user, author_user_id, created_at, updated_at
  )
  values (
    v_id, v_owner, p_conversation_id, v_role, v_content,
    case when jsonb_typeof(p_message -> 'citations') = 'array' then p_message -> 'citations' end,
    case when jsonb_typeof(p_message -> 'sources') = 'array' then p_message -> 'sources' end,
    case when jsonb_typeof(p_message -> 'answerBlocks') = 'array' then p_message -> 'answerBlocks' end,
    case when jsonb_typeof(p_message -> 'suggestions') = 'array' then p_message -> 'suggestions' end,
    coalesce((p_message ->> 'stoppedByUser')::boolean, false),
    v_uid,
    timezone('utc'::text, now()),
    timezone('utc'::text, now())
  )
  -- An existing id is never overwritten, so members cannot edit others' messages.
  on conflict (id) do nothing;

  update public.conversations
  set updated_at = timezone('utc'::text, now())
  where id = p_conversation_id;

  return v_id;
end;
$$;

revoke all on function public.append_collaborative_message(uuid, jsonb) from public, anon;
grant execute on function public.append_collaborative_message(uuid, jsonb) to authenticated;

-- Owner-only member list with display names (no emails).
create or replace function public.list_conversation_members(p_conversation_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select coalesce(jsonb_agg(
    jsonb_build_object(
      'userId', m.user_id,
      'name', public.conversation_display_name(m.user_id),
      'joinedAt', m.created_at
    )
    order by m.created_at asc
  ), '[]'::jsonb)
  from public.conversation_members m
  join public.conversations c on c.id = m.conversation_id
  where m.conversation_id = p_conversation_id
    and c.user_id = (select auth.uid());
$$;

revoke all on function public.list_conversation_members(uuid) from public, anon;
grant execute on function public.list_conversation_members(uuid) to authenticated;
