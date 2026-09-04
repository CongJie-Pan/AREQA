/**
 * Realtime session BFF route.
 *
 * This route keeps browser code on the same-origin API surface while forwarding
 * the authenticated request to FastAPI, where the standard OpenAI API key is
 * exchanged for a short-lived Realtime client secret.
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
    const upstream = await fetch(`${backendUrl}/api/v1/realtime/session`, {
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
      logger.warn('Realtime session upstream failed', { clientId, status: upstream.status });
      return createErrorResponse(
        upstreamError?.message || 'Unable to create realtime session.',
        upstreamError?.code || 'REALTIME_SESSION_FAILED',
        upstream.status >= 500 ? 503 : upstream.status,
      );
    }
    const payload = await upstream.json();
    return NextResponse.json(payload, { status: 200 });
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    if (err.name === 'AbortError') return new Response(null, { status: 499 });
    logger.error('Realtime session route failed', err, { clientId });
    return createErrorResponse('Unable to connect to realtime backend.', 'NETWORK_ERROR', 503);
  }
}
