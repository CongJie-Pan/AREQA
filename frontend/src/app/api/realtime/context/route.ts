/**
 * Realtime context BFF route.
 *
 * Browser-side Realtime tool calls use this route to fetch bounded AREQA
 * context from FastAPI without exposing backend URLs or auth handling details
 * to the voice client.
 */

import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function createErrorResponse(message: string, code: string, status: number): NextResponse {
  return NextResponse.json({ error: { message, code, status } }, { status });
}

export async function POST(request: NextRequest) {
  const clientId = getClientIdentifier(request);
  const rateLimit = checkRateLimit(clientId, { maxRequests: 60, windowMs: 60_000 });
  if (!rateLimit.allowed) {
    return createErrorResponse('Rate limit exceeded. Please try again later.', 'RATE_LIMITED', 429);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return createErrorResponse('Invalid JSON in request body', 'INVALID_REQUEST', 400);
  }

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
  const authHeader = request.headers.get('authorization');
  try {
    const upstream = await fetch(`${backendUrl}/api/v1/realtime/context`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify(body),
      signal: request.signal,
    });
    if (!upstream.ok) {
      logger.warn('Realtime context upstream failed', { clientId, status: upstream.status });
      return createErrorResponse('Unable to fetch realtime context.', 'REALTIME_CONTEXT_FAILED', 503);
    }
    return NextResponse.json(await upstream.json(), { status: 200 });
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    if (err.name === 'AbortError') return new Response(null, { status: 499 });
    logger.error('Realtime context route failed', err, { clientId });
    return createErrorResponse('Unable to connect to realtime backend.', 'NETWORK_ERROR', 503);
  }
}
