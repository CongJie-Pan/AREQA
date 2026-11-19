import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';
import { UUID_PATTERN, createCallerClient, statusForRpcError } from '../../../shared';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_CONTENT_LENGTH = 200_000;

interface RouteContext {
  params: Promise<{ conversationId: string }>;
}

function arrayOrNull(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null;
}

/**
 * Append one message to a collaborative conversation.
 *
 * The database function forces the owner as `user_id` and the caller as
 * author, and never overwrites an existing message id.
 */
export async function POST(request: NextRequest, context: RouteContext) {
  const { conversationId } = await context.params;
  if (!UUID_PATTERN.test(conversationId)) {
    return NextResponse.json({ error: 'Invalid conversation id.' }, { status: 400 });
  }

  const body = await request.json().catch(() => null) as Record<string, unknown> | null;
  const id = typeof body?.id === 'string' ? body.id : '';
  const role = body?.role;
  const content = body?.content;
  if (
    !UUID_PATTERN.test(id)
    || (role !== 'user' && role !== 'assistant')
    || typeof content !== 'string'
    || content.length > MAX_CONTENT_LENGTH
  ) {
    return NextResponse.json({ error: 'Invalid message.' }, { status: 400 });
  }

  const supabase = createCallerClient(request);
  if (supabase instanceof NextResponse) return supabase;

  const { error } = await supabase.rpc('append_collaborative_message', {
    p_conversation_id: conversationId,
    p_message: {
      id,
      role,
      content,
      citations: arrayOrNull(body?.citations),
      sources: arrayOrNull(body?.sources),
      answerBlocks: arrayOrNull(body?.answerBlocks),
      suggestions: arrayOrNull(body?.suggestions),
      stoppedByUser: body?.stoppedByUser === true,
    },
  });
  if (error) {
    const status = statusForRpcError(error);
    logger.warn('collab.append_failed', { conversationId, role, status, code: error.code });
    return NextResponse.json({ error: 'Unable to save the message.' }, { status });
  }

  logger.info('collab.message_appended', { conversationId, role, contentLength: content.length });
  return NextResponse.json({ id });
}
