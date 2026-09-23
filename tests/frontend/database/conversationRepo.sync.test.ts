import 'fake-indexeddb/auto';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { conversationRepo } from '@/database/repositories/conversationRepo';
import { syncService } from '@/services/syncService';
import { db } from '@/database/db';

// Mock syncService
vi.mock('@/services/syncService', () => ({
  syncService: {
    pushConversation: vi.fn(),
    deleteConversation: vi.fn(),
  }
}));

// Mock getCurrentUserId
vi.mock('@/database/db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/database/db')>();
  return {
    ...actual,
    getCurrentUserId: vi.fn(() => 'user_123'),
  };
});

describe('conversationRepo - sync intergration', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    vi.mocked(syncService.pushConversation).mockResolvedValue(true);
    await db.open();
    await db.conversations.clear();
    await db.messages.clear();
    await db.conversationSyncQueue.clear();
  });

  afterEach(async () => {
    await db.conversationSyncQueue.clear();
    await db.conversations.clear();
    await db.messages.clear();
  });

  it('create should trigger pushConversation', async () => {
    const conv = await conversationRepo.create('Test Title');
    
    expect(conv.title).toBe('Test Title');
    await vi.waitFor(() => {
      expect(syncService.pushConversation).toHaveBeenCalledOnce();
      expect(syncService.pushConversation).toHaveBeenCalledWith(
        expect.objectContaining({ id: conv.id, title: 'Test Title' })
      );
    });
    await vi.waitFor(async () => {
      expect(await db.conversationSyncQueue.get(conv.id)).toBeUndefined();
    });
  });

  it('update should trigger pushConversation', async () => {
    const conv = await conversationRepo.create('Test Title');
    vi.clearAllMocks(); // Clear the push from create()

    await conversationRepo.update(conv.id, { title: 'Updated Title' });
    
    await vi.waitFor(() => {
      expect(syncService.pushConversation).toHaveBeenCalledOnce();
      expect(syncService.pushConversation).toHaveBeenCalledWith(
        expect.objectContaining({ id: conv.id, title: 'Updated Title' })
      );
    });
    await vi.waitFor(async () => {
      expect(await db.conversationSyncQueue.get(conv.id)).toBeUndefined();
    });
  });

  it('keeps created conversations queued when cloud push fails and flushes them later', async () => {
    vi.mocked(syncService.pushConversation).mockResolvedValueOnce(false);

    const conv = await conversationRepo.create('Recoverable Title');

    await vi.waitFor(async () => {
      expect(await db.conversationSyncQueue.get(conv.id)).toEqual(expect.objectContaining({
        id: conv.id,
        retryCount: 1,
        lastError: 'Cloud conversation push was not acknowledged',
      }));
    });

    vi.mocked(syncService.pushConversation).mockResolvedValue(true);
    await conversationRepo.flushPendingCloudSync('user_123');

    expect(syncService.pushConversation).toHaveBeenLastCalledWith(expect.objectContaining({
      id: conv.id,
      title: 'Recoverable Title',
    }));
    expect(await db.conversationSyncQueue.get(conv.id)).toBeUndefined();
  });

  it('delete should trigger deleteConversation', async () => {
    const conv = await conversationRepo.create('Test Title');
    vi.clearAllMocks();

    await conversationRepo.delete(conv.id);
    
    expect(syncService.deleteConversation).toHaveBeenCalledOnce();
    expect(syncService.deleteConversation).toHaveBeenCalledWith(conv.id);
    
    const inDb = await db.conversations.get(conv.id);
    expect(inDb).toBeUndefined();
  });

  it('clearAll should NOT trigger deleteConversation', async () => {
    await conversationRepo.create('Test Title');
    vi.clearAllMocks();

    await conversationRepo.clearAll();
    
    expect(syncService.deleteConversation).not.toHaveBeenCalled();
    const count = await db.conversations.count();
    expect(count).toBe(0);
  });
});
