import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@supabase/supabase-js';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { useSharedConversationView } from '../../../../frontend/src/components/ChatContainer/useSharedConversationView';

const TOKEN = 'L-GIo3nG6ceEijhdinSsm3A3';
const viewer = { id: 'viewer' } as User;
const shared = { id: 'c1', title: 'T', createdAt: '', updatedAt: '', messages: [] };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe('useSharedConversationView', () => {
  let replace: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    window.history.replaceState({}, '', `/?share=${TOKEN}`);
    replace = vi.fn();
    Object.defineProperty(window, 'location', { value: { ...window.location, href: window.location.href, replace }, writable: true });
    vi.stubGlobal('fetch', vi.fn(async () => json(shared)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(authenticatedFetch).mockReset();
  });

  it('opens the owner view with the original conversation id', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(json({ isOwner: true, conversationId: 'orig-1' }));
    const { result } = renderHook(() => useSharedConversationView(viewer, true, vi.fn()));

    await waitFor(() => expect(result.current.sharedView).not.toBeNull());
    expect(result.current.sharedView).toMatchObject({ token: TOKEN, isOwner: true, conversationId: 'orig-1', conversation: shared });

    act(() => result.current.exitSharedView());
    expect(result.current.sharedView).toBeNull();
  });

  it('opens a read-only view for other signed-in users without an original id', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(json({ isOwner: false }));
    const { result } = renderHook(() => useSharedConversationView(viewer, true, vi.fn()));

    await waitFor(() => expect(result.current.sharedView).not.toBeNull());
    expect(result.current.sharedView?.isOwner).toBe(false);
    expect(result.current.sharedView).not.toHaveProperty('conversationId');
  });

  it('sends signed-out visitors to the public page', () => {
    renderHook(() => useSharedConversationView(null, true, vi.fn()));
    expect(replace).toHaveBeenCalledWith(`/share/${TOKEN}`);
  });

  it('reports an unavailable share and leaves the normal workspace', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ error: 'not found' }, 404)));
    vi.mocked(authenticatedFetch).mockResolvedValue(json({ isOwner: false }));
    const onUnavailable = vi.fn();
    const { result } = renderHook(() => useSharedConversationView(viewer, true, onUnavailable));

    await waitFor(() => expect(onUnavailable).toHaveBeenCalled());
    expect(result.current.sharedView).toBeNull();
  });
});
