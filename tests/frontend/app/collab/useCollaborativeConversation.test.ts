import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { authenticatedFetch, createChatStream } = vi.hoisted(() => ({
  authenticatedFetch: vi.fn(),
  createChatStream: vi.fn(),
}));
vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch }));
vi.mock('@/services/chat-stream', () => ({ createChatStream }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { useCollaborativeConversation } from '../../../../frontend/src/app/collab/[conversationId]/useCollaborativeConversation';
import { ChatStreamError } from '../../../../frontend/src/utils/error';

const CONVERSATION_ID = '3f1c2b6e-1d2a-4c3b-9a8e-123456789abc';

const conversation = {
  id: CONVERSATION_ID,
  title: 'Group study',
  createdAt: '2026-11-19T00:00:00Z',
  updatedAt: '2026-11-19T00:00:00Z',
  viewerRole: 'editor',
  viewerUserId: 'member-1',
  ownerUserId: 'owner-1',
  isCollaborative: true,
  messages: [{ id: 'm1', role: 'user', content: 'owner question', authorUserId: 'owner-1', createdAt: '2026-11-19T00:00:01Z' }],
};

const json = (status: number, body: unknown = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

describe('useCollaborativeConversation', () => {
  let appended: Array<{ role: string; content: string }>;

  beforeEach(() => {
    appended = [];
    authenticatedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/messages')) {
        appended.push(JSON.parse(String(init?.body)));
        return json(200, { id: 'x' });
      }
      return json(200, conversation);
    });
  });

  afterEach(() => {
    authenticatedFetch.mockReset();
    createChatStream.mockReset();
  });

  it('loads the conversation for a member', async () => {
    const { result } = renderHook(() => useCollaborativeConversation(CONVERSATION_ID, true));
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.conversation?.title).toBe('Group study');
  });

  it('stores the question, streams the reply, then stores the reply', async () => {
    createChatStream.mockImplementation(async (history, callbacks) => {
      expect(history.map((item: { content: string }) => item.content)).toEqual(['owner question', 'member question']);
      callbacks.onContent('Hello ');
      callbacks.onContent('group');
      callbacks.onCitations(['https://example.com']);
      callbacks.onDone();
    });
    const { result } = renderHook(() => useCollaborativeConversation(CONVERSATION_ID, true));
    await waitFor(() => expect(result.current.status).toBe('ready'));

    let stored = false;
    await act(async () => { stored = await result.current.send('  member question  '); });

    expect(stored).toBe(true);
    expect(appended.map((item) => [item.role, item.content])).toEqual([
      ['user', 'member question'],
      ['assistant', 'Hello group'],
    ]);
    expect(appended[1]).toEqual(expect.objectContaining({ citations: ['https://example.com'] }));
    expect(createChatStream.mock.calls[0][6]).toBe(CONVERSATION_ID);
    expect(result.current.isSending).toBe(false);
    expect(result.current.draft).toBeNull();
  });

  it('keeps the question unsent when storing it is refused', async () => {
    authenticatedFetch.mockImplementation(async (url: string) => (
      url.endsWith('/messages') ? json(403) : json(200, conversation)
    ));
    const { result } = renderHook(() => useCollaborativeConversation(CONVERSATION_ID, true));
    await waitFor(() => expect(result.current.status).toBe('ready'));

    let stored = true;
    await act(async () => { stored = await result.current.send('hi'); });
    expect(stored).toBe(false);
    expect(result.current.status).toBe('no_access');
    expect(createChatStream).not.toHaveBeenCalled();
  });

  it('reports the shared-conversation rate limit', async () => {
    createChatStream.mockImplementation(async (_history, callbacks) => {
      callbacks.onError(new ChatStreamError('API Error: 429', 429));
    });
    const { result } = renderHook(() => useCollaborativeConversation(CONVERSATION_ID, true));
    await waitFor(() => expect(result.current.status).toBe('ready'));

    await act(async () => { await result.current.send('hi'); });
    expect(result.current.notice).toBe('collabRateLimited');
    expect(appended.map((item) => item.role)).toEqual(['user']);
  });

  it('shows no access when the owner removed the member', async () => {
    authenticatedFetch.mockResolvedValue(json(403));
    const { result } = renderHook(() => useCollaborativeConversation(CONVERSATION_ID, true));
    await waitFor(() => expect(result.current.status).toBe('no_access'));
  });
});
