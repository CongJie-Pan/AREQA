/** Authenticated, bounded proxy for semantic message routing. */
import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const authorization = request.headers.get('authorization');
  if (!authorization?.startsWith('Bearer ')) return NextResponse.json({ error: 'Sign in required' }, { status: 401 });
  if (!checkRateLimit(`message-intent:${getClientIdentifier(request)}`, { maxRequests: 30, windowMs: 60_000 }).allowed) {
    return NextResponse.json({ error: 'Message routing rate limit exceeded' }, { status: 429 });
  }
  if (Number(request.headers.get('content-length')) > 100_000) return NextResponse.json({ error: 'Request too large' }, { status: 413 });
  let payload: Record<string, unknown>;
  try {
    const body: unknown = await request.json();
    if (!body || typeof body !== 'object') throw new Error('Invalid body');
    payload = body as Record<string, unknown>;
    if (typeof payload.prompt !== 'string' || !payload.prompt.trim() || payload.prompt.length > 20000
      || !Number.isInteger(payload.attachment_count) || Number(payload.attachment_count) < 0 || Number(payload.attachment_count) > 5
      || !Array.isArray(payload.context) || payload.context.length > 6
      || payload.context.some((item: unknown) => {
        if (!item || typeof item !== 'object') return true;
        const value = item as Record<string, unknown>;
        return typeof value.id !== 'string' || value.id.length < 1 || value.id.length > 128
          || !['user', 'assistant'].includes(String(value.role)) || typeof value.content !== 'string'
          || value.content.length > 1800 || typeof value.has_image !== 'boolean';
      })) throw new Error('Invalid fields');
  } catch {
    return NextResponse.json({ error: 'Invalid routing request' }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000'}/api/v1/images/intent`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: authorization },
      body: JSON.stringify(payload), signal: request.signal,
    });
    if (!upstream.ok) return NextResponse.json({ error: 'Message routing unavailable' }, { status: upstream.status });
    return NextResponse.json(await upstream.json());
  } catch (error) {
    logger.warn('message_intent_proxy_failed', { reason: error instanceof Error ? error.name : 'UnknownError' });
    return NextResponse.json({ error: 'Message routing unavailable' }, { status: 503 });
  }
}
