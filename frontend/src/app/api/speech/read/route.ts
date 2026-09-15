/**
 * Text-to-speech BFF route.
 *
 * Generates speech from assistant-authored text through OpenAI while keeping
 * OPENAI_API_KEY server-side.
 */

import { NextRequest, NextResponse } from 'next/server';
import { checkRateLimit, getClientIdentifier, logger } from '@/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const OPENAI_SPEECH_URL = 'https://api.openai.com/v1/audio/speech';
const TTS_MODEL = process.env.OPENAI_TTS_MODEL || 'gpt-4o-mini-tts';
const TTS_VOICE = process.env.OPENAI_TTS_VOICE || 'cedar';
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
      error?: { message?: string; code?: string };
    };
    if (payload.error?.message) {
      return { message: payload.error.message, code: payload.error.code || 'OPENAI_TTS_ERROR' };
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

  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    logger.warn('Speech read aloud unavailable: missing OpenAI API key', { clientId });
    return createErrorResponse('Read aloud is not configured.', 'TTS_NOT_CONFIGURED', 503);
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

  try {
    logger.info('Speech read aloud requested', {
      clientId,
      model: TTS_MODEL,
      voice: TTS_VOICE,
      inputChars: input.length,
      wasTruncated: text.length > input.length,
    });

    const upstream = await fetch(OPENAI_SPEECH_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: TTS_MODEL,
        voice: TTS_VOICE,
        input,
        response_format: 'mp3',
        instructions: 'Read clearly in a warm, natural tutoring tone.',
      }),
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
