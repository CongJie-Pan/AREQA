/**
 * Chat API Route (BFF Proxy)
 * Proxies requests to local Python FastAPI backend `/api/stream` and handles SSE streaming
 * Includes rate limiting, input validation, and zero-copy stream chunking
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  validateMessagesArray,
  checkRateLimit,
  getClientIdentifier,
  logger,
} from '@/utils';

// Ensure Node.js runtime and force-dynamic for streaming
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_ATTACHMENT_COUNT = 5;
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const SUPPORTED_ATTACHMENT_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'application/pdf',
  'text/plain',
  'text/markdown',
]);

interface ChatRequestBody {
  messages: Array<{ role: string; content: string }>;
  conversation_id?: string;
  use_rag?: boolean;
  use_web_search?: boolean;
  search_mode?: 'auto' | 'always' | 'never';
  interface_language?: 'zh-TW' | 'zh-CN' | 'en';
  force_think?: boolean;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  repetition_penalty?: number;
}

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

function validateAttachments(files: File[]): string | null {
  if (files.length > MAX_ATTACHMENT_COUNT) {
    return `每次最多可附加 ${MAX_ATTACHMENT_COUNT} 個檔案。`;
  }

  let totalSize = 0;
  for (const file of files) {
    if (!SUPPORTED_ATTACHMENT_TYPES.has(file.type)) {
      return '僅支援 PNG、JPEG、WEBP、GIF、PDF、TXT 與 Markdown 檔案。';
    }
    if (file.size === 0) return '不接受空白附件。';
    if (file.size > MAX_ATTACHMENT_BYTES) return '單一附件不得超過 5 MB。';
    totalSize += file.size;
  }

  return totalSize > MAX_TOTAL_ATTACHMENT_BYTES ? '附件總大小不得超過 20 MB。' : null;
}

export async function POST(request: NextRequest) {
  const clientId = getClientIdentifier(request);

  try {
    // Rate limiting
    const rateLimit = checkRateLimit(clientId, {
      maxRequests: 20,
      windowMs: 60_000,
    });

    if (!rateLimit.allowed) {
      logger.warn('Rate limit exceeded', { clientId, resetIn: rateLimit.resetIn });
      return createErrorResponse(
        `Rate limit exceeded. Please retry after ${rateLimit.resetIn} seconds.`,
        'RATE_LIMITED',
        429,
        rateLimit.resetIn,
        createRateLimitHeaders(rateLimit.remaining, rateLimit.limit, rateLimit.resetIn)
      );
    }

    const isMultipart = request.headers.get('content-type')?.startsWith('multipart/form-data') ?? false;
    let body: ChatRequestBody;
    let outgoingBody: BodyInit;
    let isAttachmentRequest = false;

    try {
      if (isMultipart) {
        const formData = await request.formData();
        const rawMessages = formData.get('messages');
        if (typeof rawMessages !== 'string') {
          return createErrorResponse('Missing messages field', 'INVALID_MESSAGES', 400);
        }
        body = JSON.parse(rawMessages) as ChatRequestBody;
        const files = formData.getAll('attachments').filter((entry): entry is File => entry instanceof File);
        const attachmentError = validateAttachments(files);
        if (attachmentError) {
          return createErrorResponse(attachmentError, 'INVALID_ATTACHMENT', 413);
        }
        isAttachmentRequest = true;
        outgoingBody = formData;
      } else {
        body = await request.json() as ChatRequestBody;
        outgoingBody = JSON.stringify({
          messages: body.messages,
          conversation_id: body.conversation_id || '',
          use_rag: body.use_rag || false,
          use_web_search: body.use_web_search || false,
          search_mode: body.search_mode,
          interface_language: body.interface_language,
          force_think: body.force_think || false,
          temperature: body.temperature ?? 0.0,
          top_p: body.top_p ?? 0.9,
          max_tokens: body.max_tokens ?? 2048,
          repetition_penalty: body.repetition_penalty ?? 1.1,
        });
      }
    } catch {
      return createErrorResponse(isMultipart ? 'Invalid multipart request' : 'Invalid JSON in request body', 'INVALID_REQUEST', 400);
    }

    // Validate messages
    const validation = validateMessagesArray(body.messages);
    if (!validation.valid) {
      logger.warn('Message validation failed', { clientId, error: validation.error });
      return createErrorResponse(validation.error || 'Invalid messages', 'INVALID_MESSAGES', 400);
    }

    // FASTAPI TARGET
    // Replace the external perplexity endpoint with the internal FastAPI microservice
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
    const fastApiUrl = `${backendUrl}/api/v1/stream`;

    logger.info(`Forwarding chat request to internal backend: ${fastApiUrl}`);

    const authHeader = request.headers.get('authorization');

    // Forward request to internal FastAPI backend with the AbortSignal
    const fastApiResponse = await fetch(fastApiUrl, {
      method: 'POST',
      headers: {
        ...(!isAttachmentRequest ? { 'Content-Type': 'application/json' } : {}),
        ...(authHeader ? { 'Authorization': authHeader } : {})
      },
      body: outgoingBody,
      // The signal allows cancelling the local FastAPI fetch if the user closes the Next.js connection
      signal: request.signal,
    });

    if (!fastApiResponse.ok) {
      const status = fastApiResponse.status;
      logger.error('FastAPI backend error', undefined, { status, clientId });

      // Translate specific upstream error codes into well-typed client responses
      if (status === 401) {
        return createErrorResponse(
          'Authentication failed with the AI service.',
          'AUTHENTICATION_ERROR',
          401
        );
      }

      if (status === 429) {
        const retryAfter = parseInt(fastApiResponse.headers.get('Retry-After') || '60', 10);
        return createErrorResponse(
          'AI service is busy. Please try again later.',
          'SERVICE_BUSY',
          429,
          retryAfter,
          { 'Retry-After': String(retryAfter) }
        );
      }

      if (status === 503 || status === 500) {
        return createErrorResponse(
          'AI service is temporarily unavailable. Please try again later.',
          'SERVICE_UNAVAILABLE',
          503
        );
      }
      return createErrorResponse('An error occurred while processing', 'SERVICE_ERROR', 502);
    }

    if (!fastApiResponse.body) {
      return createErrorResponse('Empty response from backend', 'EMPTY_RESPONSE', 502);
    }

    // Return the SSE stream with Zero-copy pipeline caching disabled
    // X-Accel-Buffering: no prevents Nginx reverse proxies from buffering SSE chunks
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
    const err = error instanceof Error ? error : new Error(String(error));
    
    if (err.name === 'AbortError' || err.name === 'ResponseAborted') {
      logger.info('Request aborted or connection closed', { 
        clientId, 
        errorName: err.name,
        message: err.message 
      });
      return new Response(null, { status: 499 }); 
    }

    logger.error('Chat API unexpected error', err, { clientId });
    
    if (error instanceof TypeError && error.message.includes('fetch')) {
      return createErrorResponse('Unable to connect to internal AI service.', 'NETWORK_ERROR', 503);
    }

    return createErrorResponse('An unexpected error occurred.', 'INTERNAL_ERROR', 500);
  }
}
