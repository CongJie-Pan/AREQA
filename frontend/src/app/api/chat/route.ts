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
const GENERIC_TEXT_UPLOAD_TYPES = new Set(['', 'application/octet-stream', 'text/plain', 'text/markdown']);

interface ChatRequestBody {
  messages: Array<{ role: string; content: string }>;
  conversation_id?: string;
  use_rag?: boolean;
  use_web_search?: boolean;
  search_mode?: 'auto' | 'always' | 'never';
  interface_language?: 'zh-TW' | 'zh-CN' | 'en';
  tutor_profile?: 'general' | 'english';
  response_mode?: 'text' | 'voice';
  speaking_practice?: boolean;
  force_think?: boolean;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  repetition_penalty?: number;
}

type AttachmentValidationCode =
  | 'ATTACHMENT_COUNT_EXCEEDED'
  | 'ATTACHMENT_UNSUPPORTED_TYPE'
  | 'ATTACHMENT_INVALID_CONTENT'
  | 'ATTACHMENT_TOO_LARGE'
  | 'ATTACHMENT_TOTAL_SIZE_EXCEEDED';

interface AttachmentValidationError {
  code: AttachmentValidationCode;
  message: string;
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

const ATTACHMENT_ERROR_MESSAGES: Record<
  NonNullable<ChatRequestBody['interface_language']>,
  Record<AttachmentValidationCode, string>
> = {
  'zh-TW': {
    ATTACHMENT_COUNT_EXCEEDED: `每次最多可附加 ${MAX_ATTACHMENT_COUNT} 個檔案。`,
    ATTACHMENT_UNSUPPORTED_TYPE: '僅支援 PNG、JPEG、WEBP、GIF、PDF、TXT 與 Markdown 檔案。',
    ATTACHMENT_INVALID_CONTENT: '不接受空白附件。',
    ATTACHMENT_TOO_LARGE: '單一附件不得超過 5 MB。',
    ATTACHMENT_TOTAL_SIZE_EXCEEDED: '附件總大小不得超過 20 MB。',
  },
  'zh-CN': {
    ATTACHMENT_COUNT_EXCEEDED: `每次最多可附加 ${MAX_ATTACHMENT_COUNT} 个文件。`,
    ATTACHMENT_UNSUPPORTED_TYPE: '仅支持 PNG、JPEG、WEBP、GIF、PDF、TXT 与 Markdown 文件。',
    ATTACHMENT_INVALID_CONTENT: '不接受空白附件。',
    ATTACHMENT_TOO_LARGE: '单一附件不得超过 5 MB。',
    ATTACHMENT_TOTAL_SIZE_EXCEEDED: '附件总大小不得超过 20 MB。',
  },
  en: {
    ATTACHMENT_COUNT_EXCEEDED: `You can attach up to ${MAX_ATTACHMENT_COUNT} files at a time.`,
    ATTACHMENT_UNSUPPORTED_TYPE: 'Only PNG, JPEG, WEBP, GIF, PDF, TXT, and Markdown files are supported.',
    ATTACHMENT_INVALID_CONTENT: 'Empty attachments are not accepted.',
    ATTACHMENT_TOO_LARGE: 'Each attachment must be 5 MB or smaller.',
    ATTACHMENT_TOTAL_SIZE_EXCEEDED: 'Total attachment size must be 20 MB or smaller.',
  },
};

function interfaceLanguage(language: ChatRequestBody['interface_language']): NonNullable<ChatRequestBody['interface_language']> {
  return language === 'zh-CN' || language === 'en' ? language : 'zh-TW';
}

function localizeAttachmentError(
  code: string | undefined,
  fallbackMessage: string,
  language: ChatRequestBody['interface_language'],
  translateAll = false,
): string {
  const messages = ATTACHMENT_ERROR_MESSAGES[interfaceLanguage(language)];
  return code && code in messages && (translateAll || code === 'ATTACHMENT_UNSUPPORTED_TYPE')
    ? messages[code as AttachmentValidationCode]
    : fallbackMessage;
}

async function readUpstreamError(response: Response): Promise<{ message: string; code: string } | null> {
  try {
    const payload = await response.json() as {
      detail?: string | { message?: string; code?: string };
      error?: { message?: string; code?: string };
    };
    if (payload.error?.message) {
      return {
        message: payload.error.message,
        code: payload.error.code || 'SERVICE_ERROR',
      };
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
    // Fall through to the generic upstream message below.
  }

  return null;
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

function validateAttachments(files: File[]): AttachmentValidationError | null {
  if (files.length > MAX_ATTACHMENT_COUNT) {
    return {
      code: 'ATTACHMENT_COUNT_EXCEEDED',
      message: ATTACHMENT_ERROR_MESSAGES['zh-TW'].ATTACHMENT_COUNT_EXCEEDED,
    };
  }

  let totalSize = 0;
  for (const file of files) {
    if (!isSupportedAttachment(file)) {
      return {
        code: 'ATTACHMENT_UNSUPPORTED_TYPE',
        message: ATTACHMENT_ERROR_MESSAGES['zh-TW'].ATTACHMENT_UNSUPPORTED_TYPE,
      };
    }
    if (file.size === 0) {
      return {
        code: 'ATTACHMENT_INVALID_CONTENT',
        message: ATTACHMENT_ERROR_MESSAGES['zh-TW'].ATTACHMENT_INVALID_CONTENT,
      };
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      return {
        code: 'ATTACHMENT_TOO_LARGE',
        message: ATTACHMENT_ERROR_MESSAGES['zh-TW'].ATTACHMENT_TOO_LARGE,
      };
    }
    totalSize += file.size;
  }

  return totalSize > MAX_TOTAL_ATTACHMENT_BYTES
    ? {
        code: 'ATTACHMENT_TOTAL_SIZE_EXCEEDED',
        message: ATTACHMENT_ERROR_MESSAGES['zh-TW'].ATTACHMENT_TOTAL_SIZE_EXCEEDED,
      }
    : null;
}

function isSupportedAttachment(file: File): boolean {
  if (SUPPORTED_ATTACHMENT_TYPES.has(file.type)) return true;
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  return ['txt', 'md'].includes(extension) && GENERIC_TEXT_UPLOAD_TYPES.has(file.type);
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
          return createErrorResponse(
            localizeAttachmentError(attachmentError.code, attachmentError.message, body.interface_language, true),
            attachmentError.code,
            413,
          );
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
          tutor_profile: body.tutor_profile === 'english' ? 'english' : 'general',
          response_mode: body.response_mode === 'voice' ? 'voice' : 'text',
          speaking_practice: body.speaking_practice === true,
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
      const upstreamError = await readUpstreamError(fastApiResponse);

      // Translate specific upstream error codes into well-typed client responses
      if (status === 401) {
        return createErrorResponse(
          upstreamError?.message || 'Authentication failed with the AI service.',
          upstreamError?.code || 'AUTHENTICATION_ERROR',
          401
        );
      }

      if (status === 429) {
        const retryAfter = parseInt(fastApiResponse.headers.get('Retry-After') || '60', 10);
        return createErrorResponse(
          upstreamError?.message || 'AI service is busy. Please try again later.',
          upstreamError?.code || 'SERVICE_BUSY',
          429,
          retryAfter,
          { 'Retry-After': String(retryAfter) }
        );
      }

      if (status === 400 || status === 413 || status === 422) {
        return createErrorResponse(
          localizeAttachmentError(
            upstreamError?.code,
            upstreamError?.message || 'An error occurred while processing',
            body.interface_language,
          ),
          upstreamError?.code || 'SERVICE_ERROR',
          status,
        );
      }

      if (status === 503 || status === 500) {
        return createErrorResponse(
          upstreamError?.message || 'AI service is temporarily unavailable. Please try again later.',
          upstreamError?.code || 'SERVICE_UNAVAILABLE',
          503
        );
      }
      return createErrorResponse(
        upstreamError?.message || 'An error occurred while processing',
        upstreamError?.code || 'SERVICE_ERROR',
        502,
      );
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
