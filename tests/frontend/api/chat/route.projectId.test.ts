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

const PROJECT = '7a1c2b6e-1d2a-4c3b-9a8e-123456789abc';
const forwarded = () => JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body));

function jsonRequest(body: unknown) {
  return {
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    signal: new AbortController().signal,
  };
}

describe('chat BFF route: project id', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('data: [DONE]\n\n', { status: 200 })));
  });

  it('forwards a valid project id', async () => {
    await POST(jsonRequest({ messages: [{ role: 'user', content: 'hi' }], project_id: PROJECT }) as never);
    expect(forwarded().project_id).toBe(PROJECT);
  });

  it.each([undefined, '', 'not-a-uuid', 42, `${PROJECT}' or 1=1`])('drops %s', async (projectId) => {
    await POST(jsonRequest({ messages: [{ role: 'user', content: 'hi' }], project_id: projectId }) as never);
    expect(forwarded()).not.toHaveProperty('project_id');
  });
});
