import { describe, expect, it, beforeEach, vi } from 'vitest';

import { POST } from '@/app/api/chat/route';

vi.mock('@/utils', () => ({
  validateMessagesArray: vi.fn(() => ({ valid: true })),
  checkRateLimit: vi.fn(() => ({ allowed: true, remaining: 19, limit: 20, resetIn: 60 })),
  getClientIdentifier: vi.fn(() => 'test-client'),
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('next/server', () => ({
  NextResponse: {
    json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init),
  },
}));

function sseResponse(): Response {
  return new Response('data: [DONE]\n\n', { status: 200 });
}

function multipartRequest(formData: FormData, authorization?: string) {
  return {
    headers: new Headers({
      'content-type': 'multipart/form-data; boundary=test-boundary',
      ...(authorization ? { authorization } : {}),
    }),
    formData: async () => formData,
    signal: new AbortController().signal,
  };
}

describe('chat attachment BFF route', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse()));
  });

  it('validates and forwards multipart attachments without forcing a content type', async () => {
    const formData = new FormData();
    formData.append('messages', JSON.stringify({ messages: [{ role: 'user', content: '請閱讀附件' }] }));
    formData.append('attachments', new File(['notes'], 'notes.txt', { type: 'text/plain' }));
    const request = multipartRequest(formData, 'Bearer test-token');

    const response = await POST(request as any);
    const upstreamRequest = vi.mocked(fetch).mock.calls[0][1] as RequestInit;

    expect(response.status).toBe(200);
    expect(upstreamRequest.body).toBeInstanceOf(FormData);
    expect(new Headers(upstreamRequest.headers).get('Content-Type')).toBeNull();
    expect(new Headers(upstreamRequest.headers).get('Authorization')).toBe('Bearer test-token');
  });

  it('rejects an unsupported attachment before forwarding the request', async () => {
    const formData = new FormData();
    formData.append('messages', JSON.stringify({ messages: [{ role: 'user', content: '請閱讀附件' }] }));
    formData.append('attachments', new File(['binary'], 'program.exe', { type: 'application/octet-stream' }));
    const request = multipartRequest(formData);

    const response = await POST(request as any);

    expect(response.status).toBe(413);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('preserves backend attachment validation errors instead of masking them', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: 'ATTACHMENT_INVALID_CONTENT',
              message: 'Uploaded image could not be decoded.',
            },
          }),
          { status: 422, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );
    const formData = new FormData();
    formData.append('messages', JSON.stringify({ messages: [{ role: 'user', content: '請幫我解釋這張圖' }] }));
    formData.append('attachments', new File(['not-a-real-png'], 'pasted-image.png', { type: 'image/png' }));
    const request = multipartRequest(formData);

    const response = await POST(request as any);
    const payload = await response.json();

    expect(response.status).toBe(422);
    expect(payload.error).toMatchObject({
      code: 'ATTACHMENT_INVALID_CONTENT',
      message: 'Uploaded image could not be decoded.',
      status: 422,
    });
  });
});
