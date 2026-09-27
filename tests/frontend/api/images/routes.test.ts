import { beforeEach, describe, expect, it, vi } from 'vitest';
import { checkRateLimit } from '@/utils';

vi.mock('@/utils', () => ({
  checkRateLimit: vi.fn(() => ({ allowed: true })),
  getClientIdentifier: vi.fn(() => 'test-client'),
  logger: { warn: vi.fn(), error: vi.fn() },
}));
vi.mock('next/server', () => ({
  NextResponse: { json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init) },
}));

import { POST as generate } from '@/app/api/images/generate/route';
import { POST as refresh } from '@/app/api/images/refresh/route';
import { POST as download } from '@/app/api/images/download/route';

const request = (body: unknown, authorized = true) => ({
  headers: new Headers(authorized ? { authorization: 'Bearer user-token' } : {}),
  json: async () => body,
  signal: new AbortController().signal,
});

describe('image route proxies', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(checkRateLimit).mockReturnValue({ allowed: true, remaining: 5, limit: 6, resetIn: 60 });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ imageUrl: 'https://example.test/new.png' }))));
  });

  it('does not call the provider proxy without a bearer token', async () => {
    expect((await generate(request({ prompt: 'Draw a cat', conversation_id: 'conv-a' }, false) as never)).status).toBe(401);
    expect((await refresh(request({ conversation_id: 'conv-a', image_id: 'image-a' }, false) as never)).status).toBe(401);
    expect((await download(request({ conversation_id: 'conv-a', image_id: 'image-a' }, false) as never)).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('forwards bounded generation fields and the bearer token', async () => {
    const response = await generate(request({ prompt: 'Draw a cat', conversation_id: 'conv-a', interface_language: 'en' }) as never);
    expect(response.status).toBe(200);
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toContain('/api/v1/images/generate');
    expect(new Headers(options?.headers).get('authorization')).toBe('Bearer user-token');
  });

  it('rejects invalid refresh identifiers before calling the backend', async () => {
    const response = await refresh(request({ conversation_id: '../other', image_id: 'image-a' }) as never);
    expect(response.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('returns a private PNG download after forwarding authenticated identifiers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Blob(['png'], { type: 'image/png' }))));
    const response = await download(request({ conversation_id: 'conv-a', image_id: 'image-a' }) as never);
    expect(response.status).toBe(200);
    expect(response.headers.get('content-disposition')).toContain('attachment');
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('/api/v1/images/download');
  });
});
