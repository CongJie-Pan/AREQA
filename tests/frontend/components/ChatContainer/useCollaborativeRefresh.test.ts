import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  syncList: vi.fn(),
  loadConversations: vi.fn(),
  pull: vi.fn(),
}));

vi.mock('@/services/collaborationSync', () => ({
  COLLABORATIVE_REFRESH_INTERVAL_MS: 5000,
  COLLABORATIVE_LIST_REFRESH_INTERVAL_MS: 20000,
  syncCollaborativeConversationList: mocks.syncList,
}));
vi.mock('@/services/syncService', () => ({ syncService: { pullConversationMessages: mocks.pull } }));
vi.mock('@/services/chat', () => ({ isStreamActive: () => false, loadMessages: vi.fn() }));
vi.mock('@/store/conversation', () => ({
  useConversationStore: { getState: () => ({ loadConversations: mocks.loadConversations, activeConversationId: 'c1' }) },
}));
vi.mock('@/store/chat/store', () => ({ useChatStore: { getState: () => ({ isStreaming: false }) } }));
vi.mock('@/database/db', () => ({ db: { conversations: { get: vi.fn(async () => ({ id: 'c1' })) } } }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn() } }));

import { useCollaborativeRefresh } from '../../../../frontend/src/components/ChatContainer/useCollaborativeRefresh';

describe('useCollaborativeRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.pull.mockResolvedValue(false);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('learns that an open personal chat became shared without a reload', async () => {
    mocks.syncList.mockResolvedValue(true);
    renderHook(() => useCollaborativeRefresh({ id: 'c1' }, 'owner', vi.fn()));

    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(mocks.syncList).toHaveBeenCalledWith('owner');
    expect(mocks.loadConversations).toHaveBeenCalledWith('owner');
  });

  it('refreshes right away when the tab regains focus', async () => {
    mocks.syncList.mockResolvedValue(false);
    renderHook(() => useCollaborativeRefresh(
      { id: 'c1', collaboration: { role: 'owner', ownerUserId: 'owner' } }, 'owner', vi.fn(),
    ));

    await act(async () => { window.dispatchEvent(new Event('focus')); await vi.advanceTimersByTimeAsync(0); });
    expect(mocks.syncList).toHaveBeenCalledTimes(1);
    expect(mocks.pull).toHaveBeenCalledWith('c1', 'owner', { authoritative: true });
    expect(mocks.loadConversations).not.toHaveBeenCalled();
  });
});
