import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils', () => ({
  checkRateLimit: vi.fn(() => ({ allowed: true, remaining: 19, limit: 20, resetIn: 60 })),
  getClientIdentifier: vi.fn(() => 'test-client-id'),
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('next/server', () => ({
  NextResponse: {
    json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init),
  },
}));

import { POST } from '@/app/api/speech/read/route';
import { checkRateLimit } from '@/utils';

function jsonRequest(body: unknown) {
  return {
    json: async () => body,
    signal: new AbortController().signal,
  };
}

describe('speech read aloud API route', () => {
  const originalBackendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_BACKEND_URL = 'https://backend.example';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('mp3-bytes', {
          status: 200,
          headers: { 'content-type': 'audio/mpeg' },
        }),
      ),
    );
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_BACKEND_URL = originalBackendUrl;
    vi.unstubAllGlobals();
  });

  it('proxies assistant read-out text to the FastAPI backend', async () => {
    const response = await POST({
      ...jsonRequest({ text: '請朗讀這段回覆' }),
      headers: new Headers({ authorization: 'Bearer user-token' }),
    } as any);
    const requestInit = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(requestInit.body));

    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('audio/mpeg');
    expect(fetch).toHaveBeenCalledWith(
      'https://backend.example/api/v1/speech/read',
      expect.objectContaining({
        method: 'POST',
        headers: {
          Authorization: 'Bearer user-token',
          'Content-Type': 'application/json',
        },
      }),
    );
    expect(body).toEqual({ text: '請朗讀這段回覆' });
  });

  it('preserves backend speech generation errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: 'OPENAI_API_KEY_MISSING',
              message: 'OpenAI speech generation is not configured.',
            },
          }),
          { status: 503, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );

    const response = await POST({
      ...jsonRequest({ text: 'hello' }),
      headers: new Headers(),
    } as any);
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload.error.code).toBe('OPENAI_API_KEY_MISSING');
  });

  it('rate limits read-out generation', async () => {
    vi.mocked(checkRateLimit).mockReturnValue({ allowed: false, remaining: 0, limit: 20, resetIn: 60 });

    const response = await POST(jsonRequest({ text: 'hello' }) as any);
    const payload = await response.json();

    expect(response.status).toBe(429);
    expect(payload.error.code).toBe('RATE_LIMITED');
    expect(fetch).not.toHaveBeenCalled();
  });
});
