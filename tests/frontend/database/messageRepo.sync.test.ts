import 'fake-indexeddb/auto';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { messageRepo } from '@/database/repositories/messageRepo';
import { db } from '@/database/db';
import { syncService } from '@/services/syncService';

vi.mock('@/services/syncService', () => ({
  syncService: {
    pushMessage: vi.fn(),
    pushConversation: vi.fn(),
    deleteMessage: vi.fn(),
  },
}));

vi.mock('@/database/db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/database/db')>();
  return {
    ...actual,
    getCurrentUserId: vi.fn(() => 'user_123'),
  };
});

describe('messageRepo - sync integration', () => {
  it('reloads delayed user transcriptions before the assistant reply', async () => {
    await messageRepo.add('conv_voice', {
      id: 'reply', role: 'assistant', content: 'Answer', createdAt: new Date(2000),
    });
    await messageRepo.add('conv_voice', {
      id: 'question', role: 'user', content: 'Question', createdAt: new Date(1000),
    });
    const messages = await messageRepo.getByConversationId('conv_voice', 'user_123');
    expect(messages.map((message) => message.id)).toEqual(['question', 'reply']);
  });
  beforeEach(async () => {
    vi.clearAllMocks();
    await db.open();
    await db.conversations.clear();
    await db.messages.clear();
  });

  afterEach(async () => {
    await db.messages.clear();
    await db.conversations.clear();
  });

  it('delete should remove the local message and tombstone it in cloud sync', async () => {
    const createdAt = new Date('2026-08-08T00:00:00.000Z');
    await db.conversations.add({
      id: 'conv_1',
      userId: 'user_123',
      title: 'Edited branch',
      createdAt,
      updatedAt: createdAt,
      messageCount: 2,
      lastMessagePreview: 'Old assistant answer',
    });
    await db.messages.add({
      id: 'assistant_old',
      userId: 'user_123',
      conversationId: 'conv_1',
      role: 'assistant',
      content: 'Old assistant answer',
      createdAt,
    });

    await messageRepo.delete('assistant_old');

    expect(await db.messages.get('assistant_old')).toBeUndefined();
    expect(syncService.deleteMessage).toHaveBeenCalledWith('assistant_old');
    expect(syncService.pushMessage).not.toHaveBeenCalled();
  });
});
