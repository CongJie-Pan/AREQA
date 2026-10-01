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

import { POST as intent } from '@/app/api/images/intent/route';
import { POST as generate } from '@/app/api/images/generate/route';
import { POST as refresh } from '@/app/api/images/refresh/route';
import { POST as download } from '@/app/api/images/download/route';
import { POST as reference } from '@/app/api/images/reference/route';

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

  it('authenticates and validates semantic routing requests before forwarding', async () => {
    const body = { prompt: '幫我產圖', attachment_count: 1, context: [] };
    expect((await intent(request(body, false) as never)).status).toBe(401);
    expect((await intent(request({ ...body, context: [{ content: 'bad' }] }) as never)).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
    expect((await intent(request(body) as never)).status).toBe(200);
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain('/api/v1/images/intent');
    expect(new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers).get('authorization')).toBe('Bearer user-token');
  });

  it('does not call the provider proxy without a bearer token', async () => {
    expect((await generate(request({ prompt: 'Draw a cat', conversation_id: 'conv-a' }, false) as never)).status).toBe(401);
    expect((await refresh(request({ conversation_id: 'conv-a', image_id: 'image-a' }, false) as never)).status).toBe(401);
    expect((await download(request({ conversation_id: 'conv-a', image_id: 'image-a' }, false) as never)).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('forwards bounded generation fields and the bearer token', async () => {
    const incoming = request({ prompt: 'Draw a cat', conversation_id: 'conv-a', interface_language: 'en',
      conversation_context: 'user: The cat sits beside a blue book.' });
    const response = await generate(incoming as never);
    expect(response.status).toBe(200);
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toContain('/api/v1/images/generate');
    expect(new Headers(options?.headers).get('authorization')).toBe('Bearer user-token');
    expect(options?.signal).toBe(incoming.signal);
    expect(JSON.parse(options?.body as string).conversation_context).toContain('blue book');
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

  it('authenticates and forwards reference attachments without a JSON content type', async () => {
    const form = new FormData();
    form.set('prompt', 'Explain the source');
    form.set('conversation_id', 'conv-a');
    form.append('attachments', new File(['source'], 'lesson.txt', { type: 'text/plain' }));
    expect((await reference(request({}, false) as never)).status).toBe(401);
    const response = await reference({ ...request({}), formData: async () => form } as never);
    expect(response.status).toBe(200);
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toContain('/api/v1/images/reference');
    expect(options?.body).toBe(form);
    expect(new Headers(options?.headers).has('content-type')).toBe(false);
  });

  it('rejects oversized reference briefs before forwarding generation', async () => {
    const response = await generate(request({ prompt: 'Draw a cat', conversation_id: 'conv-a', reference_brief: 'a'.repeat(4001) }) as never);
    expect(response.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rejects oversized conversation context before forwarding generation', async () => {
    const response = await generate(request({ prompt: 'Draw a cat', conversation_id: 'conv-a',
      conversation_context: 'a'.repeat(2001) }) as never);
    expect(response.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('forwards a safe image provider error code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'IMAGE_PROVIDER_HTTP_402' },
    }), { status: 402 })));
    const result = await generate(request({ prompt: 'Draw a cat', conversation_id: 'conv-a' }) as never);
    expect(result.status).toBe(402);
    expect(await result.json()).toMatchObject({ code: 'IMAGE_PROVIDER_HTTP_402' });
  });
});
