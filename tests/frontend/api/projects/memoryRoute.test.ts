import { beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/projects/[projectId]/memory/[action]/route';

vi.mock('@/utils', () => ({ logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('next/server', () => ({
  NextResponse: { json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init) },
}));

const PROJECT = '7a1c2b6e-1d2a-4c3b-9a8e-123456789abc';

function call(action: string, { body, auth = 'Bearer jwt', projectId = PROJECT, length }: {
  body?: unknown; auth?: string | null; projectId?: string; length?: number;
} = {}) {
  const headers = new Headers();
  if (auth) headers.set('authorization', auth);
  if (length !== undefined) headers.set('content-length', String(length));
  const request = { headers, json: async () => body, signal: new AbortController().signal };
  return POST(request as never, { params: Promise.resolve({ projectId, action }) });
}

describe('project memory proxy route', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ memory: { summary: 's' } }), { status: 200 })));
  });

  it('forwards refresh with the bearer token and no body', async () => {
    const response = await call('refresh');
    expect(response.status).toBe(200);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toMatch(new RegExp(`/api/v1/projects/${PROJECT}/memory/refresh$`));
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer jwt');
    expect(init?.body).toBeUndefined();
  });

  it('forwards only a trimmed instruction for revise', async () => {
    await call('revise', { body: { instruction: '  shorter  ', extra: 'dropped' } });
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({ instruction: 'shorter' });
  });

  it.each([
    ['no token', { auth: null }, 'refresh', 401],
    ['bad project id', { projectId: 'nope' }, 'refresh', 400],
    ['unknown action', {}, 'delete', 400],
    ['empty instruction', { body: { instruction: '   ' } }, 'revise', 400],
    ['oversized instruction', { body: { instruction: 'x'.repeat(1001) } }, 'revise', 400],
    ['oversized request', { body: { instruction: 'x' }, length: 9000 }, 'revise', 413],
  ])('rejects %s before calling the backend', async (_name, options, action, status) => {
    const response = await call(action as string, options as never);
    expect(response.status).toBe(status);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('passes upstream status through with a generic error and maps network failure to 503', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response('{"detail":"private"}', { status: 404 }));
    const notFound = await call('refresh');
    expect(notFound.status).toBe(404);
    expect(await notFound.text()).not.toContain('private');

    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('network'));
    expect((await call('refresh')).status).toBe(503);
  });
});
