import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock utils
vi.mock('@/utils', () => ({
  checkRateLimit: vi.fn(),
  getClientIdentifier: vi.fn().mockReturnValue('test-client-id'),
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('next/server', () => {
  return {
    NextRequest: class MockNextRequest {
      url: string;
      method: string;
      body: any;
      signal: AbortSignal;
      constructor(url: string, init: any) {
        this.url = url;
        this.method = init?.method || 'GET';
        this.body = init?.body;
        this.signal = init?.signal || new AbortController().signal;
      }
      async json() {
        return typeof this.body === 'string' ? JSON.parse(this.body) : this.body;
      }
    },
    NextResponse: {
      json: (body: any, init?: any) => {
        return new Response(JSON.stringify(body), {
          status: init?.status || 200,
          headers: new Headers(init?.headers || {}),
        });
      }
    }
  };
});

import { POST } from '@/app/api/title/route';
import { checkRateLimit } from '@/utils';

describe('Title API Route', () => {
  const MOCK_MESSAGES = [{ role: 'user', content: 'hello' }];

  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should return 429 when rate limit is exceeded', async () => {
    vi.mocked(checkRateLimit).mockReturnValue({
      allowed: false,
      remaining: 0,
      limit: 10,
      resetIn: 60,
    });

    const request = {
      url: 'http://localhost/api/title',
      method: 'POST',
      async json() { return { messages: MOCK_MESSAGES }; },
      signal: new AbortController().signal,
    };

    const response = await POST(request as any);
    expect(response.status).toBe(429);
    const data = await response.json();
    expect(data.error.code).toBe('RATE_LIMITED');
    expect(response.headers.get('X-RateLimit-Reset')).toBe('60');
  });

  it('should correctly proxy request to FastAPI when rate limit allows', async () => {
    vi.mocked(checkRateLimit).mockReturnValue({
      allowed: true,
      remaining: 9,
      limit: 10,
      resetIn: 60,
    });

    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      body: 'mock-stream',
      status: 200,
    } as any);

    const request = {
      url: 'http://localhost/api/title',
      method: 'POST',
      async json() { return { messages: MOCK_MESSAGES }; },
      signal: new AbortController().signal,
    };

    const response = await POST(request as any);
    expect(response.status).toBe(200);
    expect(global.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/generate-title',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: MOCK_MESSAGES }),
        signal: expect.any(AbortSignal),
      })
    );
    expect(response.headers.get('Content-Type')).toBe('text/event-stream; charset=utf-8');
  });

  it('should handle internal backend errors gracefully', async () => {
    vi.mocked(checkRateLimit).mockReturnValue({
      allowed: true,
      remaining: 9,
      limit: 10,
      resetIn: 60,
    });

    vi.mocked(global.fetch).mockResolvedValue({
      ok: false,
      status: 500,
    } as any);

    const request = {
      url: 'http://localhost/api/title',
      method: 'POST',
      async json() { return { messages: MOCK_MESSAGES }; },
      signal: new AbortController().signal,
    };

    const response = await POST(request as any);
    expect(response.status).toBe(502);
    const data = await response.json();
    expect(data.error.code).toBe('SERVICE_ERROR');
  });
});
