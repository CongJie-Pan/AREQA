/** Authenticated proxy for renewing a private generated-image display URL. */

import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const clientId = getClientIdentifier(request);
  if (!checkRateLimit(`image-refresh:${clientId}`, { maxRequests: 30, windowMs: 60_000 }).allowed) {
    return NextResponse.json({ error: 'Too many image refreshes' }, { status: 429 });
  }
  const authorization = request.headers.get('authorization');
  if (!authorization?.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Sign in to view this image' }, { status: 401 });
  }
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
  if (!payload || typeof payload !== 'object') {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
  const requestBody = payload as Record<string, unknown>;
  const safeId = (value: unknown) => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
  if (!safeId(requestBody.conversation_id) || !safeId(requestBody.image_id)) {
    return NextResponse.json({ error: 'Invalid image request' }, { status: 400 });
  }
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
  try {
    const upstream = await fetch(`${backendUrl}/api/v1/images/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: authorization },
      body: JSON.stringify({ conversation_id: requestBody.conversation_id, image_id: requestBody.image_id }),
      signal: request.signal,
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: 'Image unavailable' }, { status: upstream.status });
    }
    return NextResponse.json(await upstream.json());
  } catch (error) {
    logger.warn('image_refresh_proxy_failed', { reason: error instanceof Error ? error.name : 'UnknownError' });
    return NextResponse.json({ error: 'Image unavailable' }, { status: 503 });
  }
}
