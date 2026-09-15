/**
 * Text-to-speech BFF route.
 *
 * Proxies assistant read-out text to FastAPI so the OpenAI API key stays on
 * the backend service.
 */

import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_TTS_INPUT_CHARS = 4096;

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
      return { message: payload.error.message, code: payload.error.code || 'TTS_GENERATION_FAILED' };
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
  const rateLimit = checkRateLimit(clientId, { maxRequests: 20, windowMs: 60_000 });
  if (!rateLimit.allowed) {
    return createErrorResponse('Rate limit exceeded. Please try again later.', 'RATE_LIMITED', 429);
  }

  let text = '';
  try {
    const payload = await request.json() as { text?: unknown };
    text = typeof payload.text === 'string' ? payload.text.trim() : '';
  } catch {
    return createErrorResponse('Invalid JSON request', 'INVALID_REQUEST', 400);
  }

  if (!text) {
    return createErrorResponse('Text is required.', 'TEXT_REQUIRED', 400);
  }

  const input = text.slice(0, MAX_TTS_INPUT_CHARS);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
  const authHeader = request.headers.get('authorization');

  try {
    logger.info('Speech read aloud requested', {
      clientId,
      inputChars: input.length,
      wasTruncated: text.length > input.length,
    });

    const upstream = await fetch(`${backendUrl}/api/v1/speech/read`, {
      method: 'POST',
      headers: {
        ...(authHeader ? { Authorization: authHeader } : {}),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text: input }),
      signal: request.signal,
    });

    if (!upstream.ok || !upstream.body) {
      const upstreamError = await readUpstreamError(upstream);
      logger.warn('Speech read aloud upstream failed', { clientId, status: upstream.status });
      return createErrorResponse(
        upstreamError?.message || 'Unable to generate speech.',
        upstreamError?.code || 'TTS_GENERATION_FAILED',
        upstream.status >= 500 ? 503 : upstream.status,
      );
    }

    return new Response(upstream.body, {
      status: 200,
      headers: {
        'Content-Type': upstream.headers.get('content-type') || 'audio/mpeg',
        'Cache-Control': 'no-store',
      },
    });
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    if (err.name === 'AbortError') return new Response(null, { status: 499 });
    logger.error('Speech read aloud route failed', err, { clientId });
    return createErrorResponse('Unable to connect to speech provider.', 'NETWORK_ERROR', 503);
  }
}
