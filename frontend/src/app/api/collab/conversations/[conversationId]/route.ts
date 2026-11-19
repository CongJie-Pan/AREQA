import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';
import { UUID_PATTERN, createCallerClient, statusForRpcError } from '../../shared';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface RouteContext {
  params: Promise<{ conversationId: string }>;
}

/** Load a collaborative conversation for its owner or a member. */
export async function GET(request: NextRequest, context: RouteContext) {
  const { conversationId } = await context.params;
  if (!UUID_PATTERN.test(conversationId)) {
    return NextResponse.json({ error: 'Invalid conversation id.' }, { status: 400 });
  }

  const supabase = createCallerClient(request);
  if (supabase instanceof NextResponse) return supabase;

  const { data, error } = await supabase.rpc('get_collaborative_conversation', {
    p_conversation_id: conversationId,
  });
  if (error) {
    const status = statusForRpcError(error);
    logger.warn('collab.load_failed', { conversationId, status, code: error.code });
    return NextResponse.json({ error: 'Unable to load this conversation.' }, { status });
  }
  if (!data) {
    // Not a member, removed, or the owner switched the link back to view-only.
    logger.info('collab.load_no_access', { conversationId });
    return NextResponse.json({ error: 'You no longer have access to this conversation.' }, { status: 403 });
  }

  const messageCount = Array.isArray((data as { messages?: unknown }).messages)
    ? (data as { messages: unknown[] }).messages.length
    : 0;
  logger.info('collab.loaded', { conversationId, messageCount });
  return NextResponse.json(data);
}
