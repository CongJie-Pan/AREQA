import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const SHARE_TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,80}$/;

interface RouteContext {
  params: Promise<{ token: string }>;
}

/**
 * Tell a signed-in viewer whether they own a shared conversation.
 *
 * The lookup runs with the viewer's own JWT, so the owner-only RLS policy on
 * `conversation_shares` decides: only the owner sees the row. Non-owners learn
 * nothing beyond `isOwner: false`; the owner also gets the original
 * conversation id for the "Open original chat" action.
 */
export async function GET(request: NextRequest, context: RouteContext) {
  const { token } = await context.params;
  if (!SHARE_TOKEN_PATTERN.test(token)) {
    return NextResponse.json({ error: 'Invalid share link.' }, { status: 400 });
  }

  const authHeader = request.headers.get('authorization');
  if (!authHeader) return NextResponse.json({ isOwner: false });

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    logger.error('share.viewer_config_missing');
    return NextResponse.json({ error: 'Share is not configured.' }, { status: 503 });
  }

  const supabase = createClient(url, anonKey, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });

  const { data, error } = await supabase
    .from('conversation_shares')
    .select('conversation_id')
    .eq('share_token', token)
    .is('revoked_at', null)
    .maybeSingle<{ conversation_id: string }>();

  if (error) {
    logger.warn('share.viewer_lookup_failed', { tokenLength: token.length, code: error.code });
    return NextResponse.json({ isOwner: false });
  }

  logger.info('share.viewer_resolved', { tokenLength: token.length, isOwner: Boolean(data) });
  return NextResponse.json(data
    ? { isOwner: true, conversationId: data.conversation_id }
    : { isOwner: false });
}
