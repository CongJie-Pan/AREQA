-- Collaborative conversations: who asked each question.
--
-- get_collaborative_conversation now also returns the author's avatar URL so
-- user bubbles can show the asker's avatar with their name on hover. Like
-- display names, only these two profile fields leave auth.users for people
-- who share the conversation; emails are never returned.

create or replace function public.conversation_avatar_url(p_user_id uuid)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select nullif(btrim(coalesce(
    u.raw_user_meta_data ->> 'avatar_url',
    u.raw_user_meta_data ->> 'picture',
    ''
  )), '')
  from auth.users u
  where u.id = p_user_id;
$$;

revoke all on function public.conversation_avatar_url(uuid) from public, anon, authenticated;

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
          'authorUserId', a.author_id,
          'authorName', public.conversation_display_name(a.author_id),
          'authorAvatarUrl', public.conversation_avatar_url(a.author_id),
          'createdAt', m.created_at,
          'updatedAt', coalesce(m.updated_at, m.created_at)
        )
        order by m.created_at asc
      )
      from public.messages m
      cross join lateral (select coalesce(m.author_user_id, c.user_id) as author_id) a
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
