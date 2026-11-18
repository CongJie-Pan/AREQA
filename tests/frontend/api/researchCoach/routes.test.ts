import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils', () => ({ logger: { warn: vi.fn(), info: vi.fn(), error: vi.fn() } }));
vi.mock('next/server', () => ({
  NextResponse: { json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init) },
}));

import { GET as getCard } from '@/app/api/research-coach/[conversationId]/card/route';
import { POST as confirm } from '@/app/api/research-coach/[conversationId]/confirm/route';

const ID = '8f0c2c55-1d3e-4c11-9a77-1b0e4c2f9a10';
const context = (conversationId = ID) => ({ params: Promise.resolve({ conversationId }) });
const request = (body?: unknown, authorized = true) => ({
  headers: new Headers({ ...(authorized ? { authorization: 'Bearer user-token' } : {}), 'content-length': '20' }),
  json: async () => body,
  signal: new AbortController().signal,
});

describe('topic card proxy routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ stage: 0, version: 0 }))));
  });

  it('requires a bearer token and a UUID conversation before forwarding', async () => {
    expect((await getCard(request(undefined, false) as never, context())).status).toBe(401);
    expect((await getCard(request() as never, context('../secrets'))).status).toBe(400);
    expect((await confirm(request({ version: 0 }, false) as never, context())).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('forwards reads with the user token only', async () => {
    const response = await getCard(request() as never, context());

    expect(response.status).toBe(200);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain(`/api/v1/research-coach/${ID}/card`);
    expect(init?.method).toBe('GET');
    expect(new Headers(init?.headers).get('authorization')).toBe('Bearer user-token');
  });

  it('forwards only a validated version on confirm', async () => {
    expect((await confirm(request({ version: -1 }) as never, context())).status).toBe(400);
    expect((await confirm(request({ version: '1' }) as never, context())).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();

    await confirm(request({ version: 2, stage: 6, extra: 'x' }) as never, context());
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ version: 2 });
  });

  it('returns generic errors for upstream failures', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response('{"detail":"Conversation not found"}', { status: 404 }));
    const notFound = await getCard(request() as never, context());
    expect(notFound.status).toBe(404);
    expect(await notFound.json()).toEqual({ error: 'Topic card unavailable' });

    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('network down'));
    expect((await getCard(request() as never, context())).status).toBe(503);
  });
});
