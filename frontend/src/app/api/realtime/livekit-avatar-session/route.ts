/**
 * LiveKit avatar session BFF route.
 *
 * This route keeps LiveKit API credentials on the FastAPI backend while giving
 * browser code a same-origin endpoint for short-lived room join metadata.
 */

import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface ErrorResponse {
  error: {
    message: string;
    code: string;
    status: number;
  };
}

function createErrorResponse(message: string, code: string, status: number): NextResponse<ErrorResponse> {
  return NextResponse.json({ error: { message, code, status } }, { status });
}

async function readUpstreamError(response: Response): Promise<{ message: string; code: string } | null> {
  try {
    const payload = await response.json() as {
      detail?: string | { message?: string; code?: string };
      error?: { message?: string; code?: string };
    };
    if (payload.error?.message) {
      return { message: payload.error.message, code: payload.error.code || 'SERVICE_ERROR' };
    }
    if (typeof payload.detail === 'string') {
      return { message: payload.detail, code: 'UPSTREAM_VALIDATION_ERROR' };
    }
    if (payload.detail?.message) {
      return {
        message: payload.detail.message,
        code: payload.detail.code || 'UPSTREAM_VALIDATION_ERROR',
      };
    }
  } catch {
    // Fall through to a generic upstream message.
  }
  return null;
}

/**
 * Forward avatar-mode session creation to FastAPI.
 *
 * Args:
 *   request: Browser request containing Live Tutor correlation metadata.
 *
 * Returns:
 *   Browser-safe LiveKit URL and token metadata, or a normalized error.
 *
 * Side Effects:
 *   Emits safe route-level logs. Authorization headers are forwarded but never
 *   logged; token response bodies are returned directly to the authenticated
 *   caller and excluded from logs.
 */
export async function POST(request: NextRequest) {
  const clientId = getClientIdentifier(request);
  const rateLimit = checkRateLimit(clientId, { maxRequests: 12, windowMs: 60_000 });
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
    const upstream = await fetch(`${backendUrl}/api/v1/realtime/livekit-avatar-session`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify(body),
      signal: request.signal,
    });
    if (!upstream.ok) {
      const upstreamError = await readUpstreamError(upstream);
      logger.warn('LiveKit avatar session upstream failed', { clientId, status: upstream.status });
      return createErrorResponse(
        upstreamError?.message || 'Unable to create LiveKit avatar session.',
        upstreamError?.code || 'LIVEKIT_AVATAR_SESSION_FAILED',
        upstream.status >= 500 ? 503 : upstream.status,
      );
    }
    const payload = await upstream.json();
    return NextResponse.json(payload, { status: 200 });
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    if (err.name === 'AbortError') return new Response(null, { status: 499 });
    logger.error('LiveKit avatar session route failed', err, { clientId });
    return createErrorResponse('Unable to connect to realtime backend.', 'NETWORK_ERROR', 503);
  }
}
