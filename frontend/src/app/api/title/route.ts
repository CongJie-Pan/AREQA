/**
 * Title Generation API Route (BFF Proxy)
 * Proxies requests to local Python FastAPI backend `/api/generate_title` and handles SSE streaming
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  checkRateLimit,
  getClientIdentifier,
  logger,
} from '@/utils';

// Ensure Node.js runtime and force-dynamic for streaming
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Error response structure */
interface ErrorResponse {
  error: {
    message: string;
    code: string;
    status: number;
    retryAfter?: number;
  };
}

function createErrorResponse(
  message: string,
  code: string,
  status: number,
  retryAfter?: number,
  headers?: Record<string, string>
): NextResponse<ErrorResponse> {
  const errorBody: ErrorResponse = {
    error: {
      message,
      code,
      status,
      ...(retryAfter && { retryAfter }),
    },
  };

  return NextResponse.json(errorBody, {
    status,
    headers: headers || {},
  });
}

function createRateLimitHeaders(
  remaining: number,
  limit: number,
  resetIn: number
): Record<string, string> {
  return {
    'X-RateLimit-Limit': String(limit),
    'X-RateLimit-Remaining': String(remaining),
    'X-RateLimit-Reset': String(resetIn),
  };
}

export async function POST(request: NextRequest) {
  const clientId = getClientIdentifier(request);

  try {
    // Rate limiting (shared with chat for simplicity or separate if needed)
    // Here we use a slightly more restrictive limit for title generation
    const rateLimit = checkRateLimit(clientId + '_title', {
      maxRequests: 10,
      windowMs: 60_000,
    });

    if (!rateLimit.allowed) {
      logger.warn('Title Rate limit exceeded', { clientId, resetIn: rateLimit.resetIn });
      return createErrorResponse(
        `Rate limit exceeded. Please retry after ${rateLimit.resetIn} seconds.`,
        'RATE_LIMITED',
        429,
        rateLimit.resetIn,
        createRateLimitHeaders(rateLimit.remaining, rateLimit.limit, rateLimit.resetIn)
      );
    }

    // Parse request body
    let body: { 
      messages: Array<{ role: string; content: string }>;
    };
    try {
      body = await request.json();
    } catch {
      return createErrorResponse('Invalid JSON in request body', 'INVALID_JSON', 400);
    }

    // FASTAPI TARGET
    const fastApiUrl = 'http://127.0.0.1:8000/api/v1/generate-title';

    logger.info(`Forwarding title request to internal backend: ${fastApiUrl}`);

    // Forward request to internal FastAPI backend with the AbortSignal
    const fastApiResponse = await fetch(fastApiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        messages: body.messages,
      }),
      signal: request.signal,
    });

    if (!fastApiResponse.ok) {
      const status = fastApiResponse.status;
      logger.error('FastAPI title backend error', undefined, { status, clientId });
      return createErrorResponse('An error occurred while generating title', 'SERVICE_ERROR', 502);
    }

    if (!fastApiResponse.body) {
      return createErrorResponse('Empty response from backend', 'EMPTY_RESPONSE', 502);
    }

    // Return the SSE stream
    return new Response(fastApiResponse.body, {
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
        ...createRateLimitHeaders(rateLimit.remaining, rateLimit.limit, rateLimit.resetIn),
      },
    });
  } catch (error: unknown) {
    if (error instanceof Error && error.name === 'AbortError') {
      return new Response(null, { status: 499 });
    }

    logger.error('Title API unexpected error', error instanceof Error ? error : new Error(String(error)));
    return createErrorResponse('An unexpected error occurred.', 'INTERNAL_ERROR', 500);
  }
}
