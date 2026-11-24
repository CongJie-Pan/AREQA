/**
 * Shared proxy for the Topic Finder topic-card API.
 *
 * The browser never talks to the card table: these routes forward the user's
 * bearer token to FastAPI, which checks ownership. Errors stay generic and logs
 * carry only status and reason, never card content.
 */
import { NextRequest, NextResponse } from 'next/server';
import { logger } from '@/utils';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** Mirrors the backend's focus id format; ids never carry card text. */
const FOCUS_ID_PATTERN = /^[a-z_]{1,40}(:[a-z0-9_]{1,40})?$/;

/** Browser-facing action → FastAPI path segment. */
const UPSTREAM_PATH = { card: 'card', confirm: 'confirm', stage: 'stage', focus: 'focus/skip' } as const;

export async function proxyTopicCard(
  request: NextRequest,
  conversationId: string,
  action: keyof typeof UPSTREAM_PATH,
): Promise<NextResponse> {
  const authorization = request.headers.get('authorization');
  if (!authorization?.startsWith('Bearer ')) return NextResponse.json({ error: 'Sign in required' }, { status: 401 });
  if (!UUID_PATTERN.test(conversationId)) return NextResponse.json({ error: 'Invalid conversation' }, { status: 400 });

  let body: string | undefined;
  if (action !== 'card') {
    if (Number(request.headers.get('content-length')) > 1_000) return NextResponse.json({ error: 'Request too large' }, { status: 413 });
    try {
      const payload = (await request.json()) as Record<string, unknown> | null;
      if (action === 'confirm') {
        const version = payload?.version;
        if (!Number.isInteger(version) || Number(version) < 0) throw new Error('Invalid version');
        body = JSON.stringify({ version });
      } else if (action === 'focus') {
        const gapId = payload?.gap_id;
        if (typeof gapId !== 'string' || !FOCUS_ID_PATTERN.test(gapId)) throw new Error('Invalid focus');
        body = JSON.stringify({ gap_id: gapId });
      } else {
        const stage = payload?.stage;
        if (!Number.isInteger(stage) || Number(stage) < 1 || Number(stage) > 6) throw new Error('Invalid stage');
        body = JSON.stringify({ stage });
      }
    } catch {
      return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
    }
  }

  try {
    const upstream = await fetch(
      `${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000'}/api/v1/research-coach/${conversationId}/${UPSTREAM_PATH[action]}`,
      {
        method: action === 'card' ? 'GET' : 'POST',
        headers: { Authorization: authorization, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        body,
        cache: 'no-store',
        signal: request.signal,
      },
    );
    if (!upstream.ok) {
      logger.info('topic_card_proxy_upstream_error', { action, status: upstream.status });
      return NextResponse.json({ error: 'Topic card unavailable' }, { status: upstream.status });
    }
    return NextResponse.json(await upstream.json());
  } catch (error) {
    logger.warn('topic_card_proxy_failed', { action, reason: error instanceof Error ? error.name : 'UnknownError' });
    return NextResponse.json({ error: 'Topic card unavailable' }, { status: 503 });
  }
}
