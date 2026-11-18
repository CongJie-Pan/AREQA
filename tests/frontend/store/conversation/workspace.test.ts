import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readStoredWorkspace, useConversationStore } from '@/store/conversation/store';
import { databaseService } from '@/services/database';
import type { Conversation } from '@/database/schema';

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      getAll: vi.fn().mockResolvedValue([]),
      create: vi.fn(),
      delete: vi.fn(),
      update: vi.fn(),
    },
  },
}));

vi.mock('@/database/db', () => ({
  getCurrentUserId: vi.fn().mockReturnValue('test-user-id'),
}));

const row = (id: string, kind?: Conversation['kind']): Conversation => ({
  id, userId: 'test-user-id', title: id, createdAt: new Date(0), updatedAt: new Date(0),
  messageCount: 1, lastMessagePreview: '', ...(kind ? { kind } : {}),
});

describe('Conversation store workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useConversationStore.setState({
      conversations: [row('chat-1'), row('coach-1', 'research_coach')],
      activeConversationId: null,
      workspace: 'chat',
      error: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('defaults to chat and remembers the chosen workspace', () => {
    expect(readStoredWorkspace()).toBe('chat');

    useConversationStore.getState().setWorkspace('research_coach');

    expect(useConversationStore.getState().workspace).toBe('research_coach');
    expect(window.localStorage.getItem('areqa:workspace')).toBe('research_coach');
    expect(readStoredWorkspace()).toBe('research_coach');
  });

  it('ignores unknown stored values and storage failures', () => {
    window.localStorage.setItem('areqa:workspace', 'mystery');
    expect(readStoredWorkspace()).toBe('chat');

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(readStoredWorkspace()).toBe('chat');
    expect(() => useConversationStore.getState().setWorkspace('research_coach')).not.toThrow();
    expect(useConversationStore.getState().workspace).toBe('research_coach');
  });

  it('follows the workspace of a conversation opened from anywhere', () => {
    useConversationStore.getState().selectConversation('coach-1');
    expect(useConversationStore.getState().workspace).toBe('research_coach');

    useConversationStore.getState().selectConversation('chat-1');
    expect(useConversationStore.getState().workspace).toBe('chat');

    useConversationStore.getState().setWorkspace('research_coach');
    useConversationStore.getState().selectConversation('unsaved-guest-id');
    expect(useConversationStore.getState().workspace).toBe('research_coach');
  });

  it('creates chat conversations unless a kind is passed', async () => {
    vi.mocked(databaseService.conversation.create).mockImplementation(async (_title, kind) => ({
      ...row(`new-${kind}`), ...(kind === 'research_coach' ? { kind } : {}),
    }));
    useConversationStore.getState().setWorkspace('research_coach');

    await useConversationStore.getState().createConversation();
    await useConversationStore.getState().createConversation(undefined, 'research_coach');

    expect(databaseService.conversation.create).toHaveBeenNthCalledWith(1, undefined, 'chat');
    expect(databaseService.conversation.create).toHaveBeenNthCalledWith(2, undefined, 'research_coach');
  });
});
