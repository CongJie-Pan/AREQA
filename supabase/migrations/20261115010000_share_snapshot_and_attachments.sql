-- Shared conversations: snapshot cutoff, attachment thumbnails and the stopped flag.
--
-- * "Only messages up until now are shared": the owner's latest Copy link
--   records shared_until; later messages stay private until the link is
--   copied again. Existing shares (null) keep showing every message.
-- * The read-only views reuse the chat renderer, so the share payload now
--   carries display-only attachment metadata (bounded thumbnails, never file
--   bytes) and the "you stopped the response" flag.

alter table public.messages
  add column if not exists stopped_by_user boolean not null default false;

alter table public.conversation_shares
  add column if not exists shared_until timestamptz;

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
    'sharedAt', s.shared_until,
    'messages', coalesce(
      jsonb_agg(
        jsonb_build_object(
          'id', m.id,
          'role', m.role,
          'content', m.content,
          'citations', m.citations,
          'sources', m.sources,
          'answerBlocks', m.answer_blocks,
          'attachments', m.attachments,
          'stoppedByUser', m.stopped_by_user,
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
   and (s.shared_until is null or m.created_at <= s.shared_until)
  where s.share_token = p_share_token
    and s.is_public = true
    and s.revoked_at is null
  group by c.id, c.title, c.created_at, c.updated_at, s.shared_until;
$$;

revoke all on function public.get_public_conversation_share(text) from public;
grant execute on function public.get_public_conversation_share(text) to anon, authenticated;
