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
    await db.messageDeletions.clear();
  });

  afterEach(async () => {
    await db.messages.clear();
    await db.messageDeletions.clear();
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
    expect(await db.messageDeletions.get('assistant_old')).toEqual(expect.objectContaining({
      id: 'assistant_old',
      userId: 'user_123',
      conversationId: 'conv_1',
    }));
    expect(syncService.deleteMessage).toHaveBeenCalledWith('assistant_old');
    expect(syncService.pushMessage).not.toHaveBeenCalled();
  });

  it('deleteManyByConversationId should delete a paired turn, update preview, and sync tombstones', async () => {
    const createdAt = new Date('2026-08-08T00:00:00.000Z');
    await db.conversations.add({
      id: 'conv_1',
      userId: 'user_123',
      title: 'Latest turn',
      createdAt,
      updatedAt: createdAt,
      messageCount: 4,
      lastMessagePreview: 'Latest answer',
    });
    await db.messages.bulkAdd([
      {
        id: 'user_previous',
        userId: 'user_123',
        conversationId: 'conv_1',
        role: 'user',
        content: 'Previous question',
        createdAt: new Date('2026-08-08T00:00:00.000Z'),
      },
      {
        id: 'assistant_previous',
        userId: 'user_123',
        conversationId: 'conv_1',
        role: 'assistant',
        content: 'Previous answer',
        createdAt: new Date('2026-08-08T00:00:01.000Z'),
      },
      {
        id: 'user_latest',
        userId: 'user_123',
        conversationId: 'conv_1',
        role: 'user',
        content: 'Latest question',
        createdAt: new Date('2026-08-08T00:00:02.000Z'),
      },
      {
        id: 'assistant_latest',
        userId: 'user_123',
        conversationId: 'conv_1',
        role: 'assistant',
        content: 'Latest answer',
        createdAt: new Date('2026-08-08T00:00:03.000Z'),
      },
    ]);

    await messageRepo.deleteManyByConversationId('conv_1', ['user_latest', 'assistant_latest']);

    expect(await db.messages.get('user_latest')).toBeUndefined();
    expect(await db.messages.get('assistant_latest')).toBeUndefined();
    expect((await db.messageDeletions.toArray()).map((row) => row.id).sort()).toEqual([
      'assistant_latest',
      'user_latest',
    ]);
    expect((await db.messages.where('conversationId').equals('conv_1').count())).toBe(2);
    const conversation = await db.conversations.get('conv_1');
    expect(conversation?.messageCount).toBe(2);
    expect(conversation?.lastMessagePreview).toBe('Previous answer');
    expect(syncService.deleteMessage).toHaveBeenCalledWith('user_latest');
    expect(syncService.deleteMessage).toHaveBeenCalledWith('assistant_latest');
    expect(syncService.pushConversation).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'conv_1',
        messageCount: 2,
        lastMessagePreview: 'Previous answer',
      }),
    );
  });

  it('does not update local message content when cloud update fails', async () => {
    const createdAt = new Date('2026-08-08T00:00:00.000Z');
    await db.conversations.add({
      id: 'conv_1',
      userId: 'user_123',
      title: 'Editable answer',
      createdAt,
      updatedAt: createdAt,
      messageCount: 1,
      lastMessagePreview: 'Old answer',
    });
    await db.messages.add({
      id: 'assistant_edit',
      userId: 'user_123',
      conversationId: 'conv_1',
      role: 'assistant',
      content: 'Old answer',
      createdAt,
      updatedAt: createdAt,
    });
    vi.mocked(syncService.pushMessage).mockRejectedValueOnce(new Error('cloud failed'));

    await expect(messageRepo.update('assistant_edit', { content: 'New answer' })).rejects.toThrow('cloud failed');

    expect((await db.messages.get('assistant_edit'))?.content).toBe('Old answer');
  });
});
