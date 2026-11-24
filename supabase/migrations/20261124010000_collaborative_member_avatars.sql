-- Share panel: participants' avatars next to their names.
-- Uses conversation_avatar_url() from 20261124000000; owner-only and
-- display fields only, never emails.

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
      'avatarUrl', public.conversation_avatar_url(m.user_id),
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
