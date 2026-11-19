import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';
import { UUID_PATTERN, createCallerClient, statusForRpcError } from '../../../shared';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface RouteContext {
  params: Promise<{ conversationId: string }>;
}

/** Owner-only member list (display names, never emails). */
export async function GET(request: NextRequest, context: RouteContext) {
  const { conversationId } = await context.params;
  if (!UUID_PATTERN.test(conversationId)) {
    return NextResponse.json({ error: 'Invalid conversation id.' }, { status: 400 });
  }

  const supabase = createCallerClient(request);
  if (supabase instanceof NextResponse) return supabase;

  const { data, error } = await supabase.rpc('list_conversation_members', {
    p_conversation_id: conversationId,
  });
  if (error) {
    const status = statusForRpcError(error);
    logger.warn('collab.members_list_failed', { conversationId, status, code: error.code });
    return NextResponse.json({ error: 'Unable to load members.' }, { status });
  }
  return NextResponse.json({ members: Array.isArray(data) ? data : [] });
}

/**
 * Remove a member (owner) or leave (member). RLS on `conversation_members`
 * allows exactly those two cases.
 */
export async function DELETE(request: NextRequest, context: RouteContext) {
  const { conversationId } = await context.params;
  const userId = request.nextUrl.searchParams.get('userId') ?? '';
  if (!UUID_PATTERN.test(conversationId) || !UUID_PATTERN.test(userId)) {
    return NextResponse.json({ error: 'Invalid request.' }, { status: 400 });
  }

  const supabase = createCallerClient(request);
  if (supabase instanceof NextResponse) return supabase;

  const { data, error } = await supabase
    .from('conversation_members')
    .delete()
    .eq('conversation_id', conversationId)
    .eq('user_id', userId)
    .select('user_id');
  if (error) {
    const status = statusForRpcError(error);
    logger.warn('collab.member_remove_failed', { conversationId, status, code: error.code });
    return NextResponse.json({ error: 'Unable to remove member.' }, { status });
  }
  if (!Array.isArray(data) || data.length === 0) {
    return NextResponse.json({ error: 'Member not found.' }, { status: 404 });
  }

  logger.info('collab.member_removed', { conversationId });
  return NextResponse.json({ removed: true });
}
