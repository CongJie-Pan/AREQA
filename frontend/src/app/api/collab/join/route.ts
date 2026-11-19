import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';
import { SHARE_TOKEN_PATTERN, createCallerClient, statusForRpcError } from '../shared';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Join a collaborative conversation through an edit share link. */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null) as { token?: unknown } | null;
  const token = typeof body?.token === 'string' ? body.token : '';
  if (!SHARE_TOKEN_PATTERN.test(token)) {
    return NextResponse.json({ error: 'Invalid share link.' }, { status: 400 });
  }

  const supabase = createCallerClient(request);
  if (supabase instanceof NextResponse) return supabase;

  const { data, error } = await supabase.rpc('join_conversation_share', { p_share_token: token });
  if (error || typeof data !== 'string') {
    const status = error ? statusForRpcError(error) : 500;
    logger.warn('collab.join_failed', { tokenLength: token.length, status, code: error?.code });
    return NextResponse.json({ error: 'Unable to join this conversation.' }, { status });
  }

  logger.info('collab.joined', { conversationId: data });
  return NextResponse.json({ conversationId: data });
}
