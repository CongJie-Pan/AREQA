import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

const { rpc, createClient } = vi.hoisted(() => {
  const rpc = vi.fn();
  const createClient = vi.fn(() => ({ rpc }));
  return { rpc, createClient };
});
// The routes resolve the package from frontend/node_modules; mock that copy.
vi.mock('../../../../frontend/node_modules/@supabase/supabase-js', () => ({ createClient }));
vi.mock('@/utils', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { POST as join } from '../../../../frontend/src/app/api/collab/join/route';
import { GET as load } from '../../../../frontend/src/app/api/collab/conversations/[conversationId]/route';
import { POST as append } from '../../../../frontend/src/app/api/collab/conversations/[conversationId]/messages/route';
import { GET as readShare } from '../../../../frontend/src/app/api/share/[token]/route';

const TOKEN = 'L-GIo3nG6ceEijhdinSsm3A3';
const CONVERSATION_ID = '3f1c2b6e-1d2a-4c3b-9a8e-123456789abc';
const MESSAGE_ID = '7b1c2b6e-1d2a-4c3b-9a8e-123456789abc';

function request(body?: unknown, auth = 'Bearer member-jwt') {
  return {
    headers: new Headers(auth ? { authorization: auth } : {}),
    json: async () => body,
  } as unknown as NextRequest;
}
const params = { params: Promise.resolve({ conversationId: CONVERSATION_ID }) };

describe('collaborative conversation routes', () => {
  beforeEach(() => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co');
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    rpc.mockReset();
    createClient.mockClear();
  });

  it('joins through the caller JWT and returns the conversation id', async () => {
    rpc.mockResolvedValue({ data: CONVERSATION_ID, error: null });
    const response = await join(request({ token: TOKEN }));

    expect(await response.json()).toEqual({ conversationId: CONVERSATION_ID });
    expect(rpc).toHaveBeenCalledWith('join_conversation_share', { p_share_token: TOKEN });
    expect(createClient).toHaveBeenCalledWith('https://example.supabase.co', 'anon', expect.objectContaining({
      global: { headers: { Authorization: 'Bearer member-jwt' } },
    }));
  });

  it('requires sign-in to join and maps view-only links to 404', async () => {
    expect((await join(request({ token: TOKEN }, ''))).status).toBe(401);
    expect(createClient).not.toHaveBeenCalled();

    rpc.mockResolvedValue({ data: null, error: { code: 'P0002', message: 'share_not_joinable' } });
    expect((await join(request({ token: TOKEN }))).status).toBe(404);
  });

  it('rejects malformed join tokens', async () => {
    expect((await join(request({ token: 'bad' }))).status).toBe(400);
  });

  it('answers 403 when the caller no longer has access', async () => {
    rpc.mockResolvedValue({ data: null, error: null });
    expect((await load(request(), params)).status).toBe(403);
  });

  it('appends a message with only whitelisted fields', async () => {
    rpc.mockResolvedValue({ data: MESSAGE_ID, error: null });
    const response = await append(request({
      id: MESSAGE_ID,
      role: 'assistant',
      content: 'answer',
      citations: ['https://example.com'],
      user_id: 'someone-else',
      author_user_id: 'forged',
    }), params);

    expect(response.status).toBe(200);
    const [, args] = rpc.mock.calls[0];
    expect(args.p_conversation_id).toBe(CONVERSATION_ID);
    expect(args.p_message).toEqual(expect.objectContaining({ id: MESSAGE_ID, role: 'assistant', content: 'answer' }));
    expect(args.p_message).not.toHaveProperty('user_id');
    expect(args.p_message).not.toHaveProperty('author_user_id');
  });

  it('rejects invalid messages before calling the database', async () => {
    expect((await append(request({ id: 'x', role: 'user', content: 'hi' }), params)).status).toBe(400);
    expect((await append(request({ id: MESSAGE_ID, role: 'system', content: 'hi' }), params)).status).toBe(400);
    expect(rpc).not.toHaveBeenCalled();
  });

  it('maps a membership failure to 403', async () => {
    rpc.mockResolvedValue({ data: null, error: { code: '42501', message: 'not_a_member' } });
    expect((await append(request({ id: MESSAGE_ID, role: 'user', content: 'hi' }), params)).status).toBe(403);
  });

  it('tells the share page whether the link lets people join', async () => {
    rpc
      .mockResolvedValueOnce({ data: { id: CONVERSATION_ID, messages: [] }, error: null })
      .mockResolvedValueOnce({ data: 'edit', error: null });
    const response = await readShare(request(), { params: Promise.resolve({ token: TOKEN }) });
    expect(await response.json()).toEqual(expect.objectContaining({ id: CONVERSATION_ID, accessLevel: 'edit' }));
  });

  it('treats links as view-only when the access lookup is unavailable', async () => {
    rpc
      .mockResolvedValueOnce({ data: { id: CONVERSATION_ID, messages: [] }, error: null })
      .mockResolvedValueOnce({ data: null, error: { code: 'PGRST202' } });
    const response = await readShare(request(), { params: Promise.resolve({ token: TOKEN }) });
    expect((await response.json()).accessLevel).toBe('view');
  });
});
