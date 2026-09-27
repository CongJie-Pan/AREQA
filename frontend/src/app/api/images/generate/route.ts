/** Server proxy for authenticated, bounded educational image generation. */

import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const clientId = getClientIdentifier(request);
  if (!checkRateLimit(clientId, { maxRequests: 6, windowMs: 60_000 }).allowed) {
    return NextResponse.json({ error: 'Image rate limit exceeded' }, { status: 429 });
  }
  const authorization = request.headers.get('authorization');
  if (!authorization?.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Sign in to create an image' }, { status: 401 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
  if (!body || typeof body !== 'object') {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
  const payload = body as Record<string, unknown>;
  if (typeof payload.prompt !== 'string' || payload.prompt.trim().length < 3 || payload.prompt.length > 1800
    || typeof payload.conversation_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(payload.conversation_id)) {
    return NextResponse.json({ error: 'Invalid image request' }, { status: 400 });
  }
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
  try {
    const upstream = await fetch(`${backendUrl}/api/v1/images/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: authorization },
      body: JSON.stringify(payload),
      signal: request.signal,
    });
    if (!upstream.ok) {
      logger.warn('image_generation_proxy_failed', { status: upstream.status, clientId });
      return NextResponse.json({ error: 'Image generation is unavailable' }, { status: upstream.status });
    }
    return NextResponse.json(await upstream.json());
  } catch (error) {
    logger.error('image_generation_proxy_network_failed', error instanceof Error ? error : new Error(String(error)), { clientId });
    return NextResponse.json({ error: 'Image generation is unavailable' }, { status: 503 });
  }
}
