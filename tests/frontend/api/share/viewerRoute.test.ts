import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

const { maybeSingle, createClient } = vi.hoisted(() => {
  const maybeSingle = vi.fn();
  const createClient = vi.fn(() => ({
    from: () => ({ select: () => ({ eq: () => ({ is: () => ({ maybeSingle }) }) }) }),
  }));
  return { maybeSingle, createClient };
});
// The route resolves the package from frontend/node_modules; mock that copy.
vi.mock('../../../../frontend/node_modules/@supabase/supabase-js', () => ({ createClient }));
vi.mock('@/utils', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { GET } from '../../../../frontend/src/app/api/share/[token]/viewer/route';

const TOKEN = 'L-GIo3nG6ceEijhdinSsm3A3';
const request = (auth?: string) => ({ headers: new Headers(auth ? { authorization: auth } : {}) }) as unknown as NextRequest;
const call = (auth?: string, token = TOKEN) => GET(request(auth), { params: Promise.resolve({ token }) });

describe('GET /api/share/[token]/viewer', () => {
  beforeEach(() => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co');
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    maybeSingle.mockReset();
    createClient.mockClear();
  });

  it('identifies the owner through the owner-only RLS row', async () => {
    maybeSingle.mockResolvedValue({ data: { conversation_id: 'orig-1' }, error: null });
    const response = await call('Bearer owner-jwt');

    expect(await response.json()).toEqual({ isOwner: true, conversationId: 'orig-1' });
    expect(createClient).toHaveBeenCalledWith('https://example.supabase.co', 'anon', expect.objectContaining({
      global: { headers: { Authorization: 'Bearer owner-jwt' } },
    }));
  });

  it('tells other viewers only that they are not the owner', async () => {
    maybeSingle.mockResolvedValue({ data: null, error: null });
    expect(await (await call('Bearer other-jwt')).json()).toEqual({ isOwner: false });
  });

  it('answers anonymous requests without querying', async () => {
    expect(await (await call()).json()).toEqual({ isOwner: false });
    expect(createClient).not.toHaveBeenCalled();
  });

  it('rejects malformed tokens', async () => {
    expect((await call('Bearer x', 'bad')).status).toBe(400);
  });
});
