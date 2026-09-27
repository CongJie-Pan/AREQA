import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils', () => ({
  checkRateLimit: vi.fn(() => ({ allowed: true })),
  getClientIdentifier: vi.fn(() => 'test-client'),
  logger: { warn: vi.fn() },
}));

vi.mock('next/server', () => ({
  NextResponse: { json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init) },
}));

import { POST } from '@/app/api/realtime/attachments/route';

describe('realtime attachment proxy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      conversation_id: 'conv_voice', version: 'v1',
      material: { title: 'notes.txt', text: 'cobalt', truncated: false },
    }), { status: 200 })));
  });

  it('forwards the multipart body and authorization without forcing a content type', async () => {
    const form = new FormData();
    form.set('conversation_id', 'conv_voice');
    form.append('attachments', new File(['cobalt'], 'notes.txt', { type: 'text/plain' }));
    const response = await POST({
      headers: new Headers({ authorization: 'Bearer user-token' }),
      formData: async () => form,
      signal: new AbortController().signal,
    } as never);

    expect(response.status).toBe(200);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/realtime/attachments'),
      expect.objectContaining({ method: 'POST', body: form }));
    const forwarded = vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(forwarded.headers).get('authorization')).toBe('Bearer user-token');
    expect(new Headers(forwarded.headers).get('content-type')).toBeNull();
  });
});
