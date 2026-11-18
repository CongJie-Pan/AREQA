import { beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/chat/route';

vi.mock('@/utils', () => ({
  validateMessagesArray: vi.fn(() => ({ valid: true })),
  checkRateLimit: vi.fn(() => ({ allowed: true, remaining: 19, limit: 20, resetIn: 60 })),
  getClientIdentifier: vi.fn(() => 'test-client'),
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('next/server', () => ({
  NextResponse: { json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init) },
}));

function jsonRequest(body: unknown) {
  return {
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    signal: new AbortController().signal,
  };
}

const forwarded = () => JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body));

describe('chat BFF route: conversation kind', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('data: [DONE]\n\n', { status: 200 })));
  });

  it('forwards Topic Finder turns to the backend as research_coach', async () => {
    await POST(jsonRequest({ messages: [{ role: 'user', content: '你好' }], conversation_kind: 'research_coach' }) as never);
    expect(forwarded().conversation_kind).toBe('research_coach');
  });

  it.each([undefined, 'chat', 'mystery', 7])('sends %s as ordinary chat', async (kind) => {
    await POST(jsonRequest({ messages: [{ role: 'user', content: 'hi' }], ...(kind === undefined ? {} : { conversation_kind: kind }) }) as never);
    expect(forwarded().conversation_kind).toBe('chat');
  });
});
