-- Collaborative conversations inside the normal chat (replaces the separate page).
--
-- Members keep a local copy of the shared conversation in their own chat
-- history. Their client syncs it through these functions instead of the
-- owner-only tables:
--
-- * list_my_collaborative_conversations: which shared conversations the caller
--   currently has (as owner or member); a member whose access ended is simply
--   absent, so the client drops its local copy.
-- * get_collaborative_conversation: now also returns kind, updatedAt and the
--   reference metadata the chat renderer uses.
-- * append_collaborative_message: now an upsert. The local-first client pushes
--   the same message several times while an answer streams; only the
--   message's own author may update it, and nobody can overwrite others.
-- * delete_own_collaborative_message: edit/regenerate flows remove superseded
--   messages; members may only remove messages they wrote.

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
    'kind', to_jsonb(c) ->> 'kind',
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
          'searchResults', m.search_results,
          'sources', m.sources,
          'answerBlocks', m.answer_blocks,
          'suggestions', m.suggestions,
          'attachments', m.attachments,
          'requestModes', m.request_modes,
          'stoppedByUser', m.stopped_by_user,
          'authorUserId', coalesce(m.author_user_id, c.user_id),
          'authorName', public.conversation_display_name(coalesce(m.author_user_id, c.user_id)),
          'createdAt', m.created_at,
          'updatedAt', coalesce(m.updated_at, m.created_at)
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

create or replace function public.list_my_collaborative_conversations()
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  with ids as (
    select m.conversation_id as id
    from public.conversation_members m
    where m.user_id = (select auth.uid())
    union
    select s.conversation_id
    from public.conversation_shares s
    where s.owner_user_id = (select auth.uid())
      and s.access_level = 'edit'
      and s.is_public = true
      and s.revoked_at is null
  )
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', c.id,
    'title', c.title,
    'kind', to_jsonb(c) ->> 'kind',
    'role', r.role,
    'ownerUserId', c.user_id,
    'createdAt', c.created_at,
    'updatedAt', c.updated_at
  )), '[]'::jsonb)
  from ids
  join public.conversations c on c.id = ids.id
  cross join lateral (select public.conversation_access_role(c.id) as role) r
  where r.role is not null
    and public.conversation_is_collaborative(c.id);
$$;

revoke all on function public.list_my_collaborative_conversations() from public, anon;
grant execute on function public.list_my_collaborative_conversations() to authenticated;

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
    attachments, citations, search_results, sources, answer_blocks, suggestions, request_modes,
    stopped_by_user, author_user_id, created_at, updated_at
  )
  values (
    v_id, v_owner, p_conversation_id, v_role, v_content,
    case when jsonb_typeof(p_message -> 'attachments') = 'array' then p_message -> 'attachments' else '[]'::jsonb end,
    case when jsonb_typeof(p_message -> 'citations') = 'array' then p_message -> 'citations' end,
    case when jsonb_typeof(p_message -> 'searchResults') = 'array' then p_message -> 'searchResults' end,
    case when jsonb_typeof(p_message -> 'sources') = 'array' then p_message -> 'sources' end,
    case when jsonb_typeof(p_message -> 'answerBlocks') = 'array' then p_message -> 'answerBlocks' end,
    case when jsonb_typeof(p_message -> 'suggestions') = 'array' then p_message -> 'suggestions' end,
    case when jsonb_typeof(p_message -> 'requestModes') = 'array' then p_message -> 'requestModes' end,
    coalesce((p_message ->> 'stoppedByUser')::boolean, false),
    v_uid,
    timezone('utc'::text, now()),
    timezone('utc'::text, now())
  )
  -- Only the author may update a message (the streaming answer is pushed
  -- repeatedly); role, owner, author and creation time never change.
  on conflict (id) do update set
    content = excluded.content,
    attachments = excluded.attachments,
    citations = excluded.citations,
    search_results = excluded.search_results,
    sources = excluded.sources,
    answer_blocks = excluded.answer_blocks,
    suggestions = excluded.suggestions,
    request_modes = excluded.request_modes,
    stopped_by_user = excluded.stopped_by_user,
    updated_at = excluded.updated_at
  where messages.author_user_id = v_uid
    and messages.conversation_id = p_conversation_id;

  update public.conversations
  set updated_at = timezone('utc'::text, now())
  where id = p_conversation_id;

  return v_id;
end;
$$;

revoke all on function public.append_collaborative_message(uuid, jsonb) from public, anon;
grant execute on function public.append_collaborative_message(uuid, jsonb) to authenticated;

create or replace function public.delete_own_collaborative_message(
  p_conversation_id uuid,
  p_message_id uuid
)
returns boolean
language plpgsql
volatile
security definer
set search_path = public, pg_temp
as $$
begin
  if auth.uid() is null or public.conversation_access_role(p_conversation_id) is null then
    raise exception 'not_a_member' using errcode = '42501';
  end if;

  delete from public.messages m
  where m.id = p_message_id
    and m.conversation_id = p_conversation_id
    and m.author_user_id = auth.uid();

  return found;
end;
$$;

revoke all on function public.delete_own_collaborative_message(uuid, uuid) from public, anon;
grant execute on function public.delete_own_collaborative_message(uuid, uuid) to authenticated;
