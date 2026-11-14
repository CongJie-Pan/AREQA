import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { db, getCurrentUserId } from '@/database/db';
import { conversationRepo } from '@/database/repositories/conversationRepo';
import { messageRepo } from '@/database/repositories/messageRepo';
import type { AnswerBlock, Message } from '@/database/schema';
import { syncService } from '@/services/syncService';

vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: vi.fn(),
}));

vi.mock('@/services/syncService', () => ({
  syncService: {
    pushConversation: vi.fn(),
    pushMessage: vi.fn(),
    deleteConversation: vi.fn(),
  },
}));

const OWNER = 'branch-owner';
const SOURCE = 'dec7b6b3-6ce6-4643-8a55-9ed11afbb0d2';
const BRANCH = '22e06f44-223f-4b0d-a6bc-ffdfc6f03bad';
const USER_MESSAGE = '112d551a-6114-4891-9ce3-b3b36f5d1e57';
const FORK = '7b6080b2-9b07-4f5f-91a5-d47f97c723c9';
const LATER = 'c36f2c2b-4f6f-49cf-a390-a5aa24dba4d4';

const attachments = [{ name: 'source.pdf', mediaType: 'application/pdf', sizeBytes: 27_400_000 }];
const figure: AnswerBlock = {
  type: 'image_block',
  slotId: 'figure-2',
  topic: 'Research method',
  purpose: 'diagram',
  imageUrl: 'https://example.com/figure-2.png',
  sourceUrl: 'https://example.com/source.pdf',
  sourceDomain: 'example.com',
  caption: 'Figure 2',
  provider: 'pdf_attachment',
  storageBucket: 'private-pdf-visuals',
  storagePath: 'test/figure-2.png',
  safetyStatus: 'pass',
  matchConfidence: 1,
};

function sourceMessage(id: string, role: Message['role'], content: string, seconds: number): Message {
  return {
    id, role, content,
    userId: OWNER,
    conversationId: SOURCE,
    createdAt: new Date(2026, 0, 1, 0, 0, seconds),
  };
}

describe('Conversation branch persistence', () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue(OWNER);
    vi.mocked(syncService.pushConversation).mockResolvedValue(true);
    await db.open();
    await db.conversationSyncQueue.clear();
    await db.messageSyncQueue.clear();
    await db.conversations.clear();
    await db.messages.clear();

    const now = new Date(2026, 0, 1);
    await db.conversations.add({
      id: SOURCE,
      userId: OWNER,
      title: 'Source conversation',
      createdAt: now,
      updatedAt: now,
      messageCount: 3,
      lastMessagePreview: 'Later question',
    });
    await db.messages.bulkAdd([
      { ...sourceMessage(USER_MESSAGE, 'user', 'Earlier question', 0), attachments },
      { ...sourceMessage(FORK, 'assistant', 'Selected answer', 1), answerBlocks: [figure] },
      sourceMessage(LATER, 'user', 'Later question', 2),
    ]);
  });

  it('stores an inclusive snapshot and retains references to the original attachment figures', async () => {
    const branch = await conversationRepo.branch(SOURCE, FORK, BRANCH, 'Methods branch');

    expect(branch).toEqual(expect.objectContaining({
      id: BRANCH,
      userId: OWNER,
      title: 'Methods branch',
      messageCount: 2,
      lastMessagePreview: 'Selected answer',
      branchOrigin: expect.objectContaining({ conversationId: SOURCE, messageId: FORK, title: 'Source conversation' }),
    }));

    const copied = await messageRepo.getByConversationId(BRANCH, OWNER);
    expect(copied.map(({ content }) => content)).toEqual(['Earlier question', 'Selected answer']);
    expect(copied[0].id).not.toBe(USER_MESSAGE);
    expect(copied[1].id).not.toBe(FORK);
    expect(copied[0].attachments).toEqual(attachments);
    expect(copied[0].attachmentSourceId).toBe(USER_MESSAGE);
    expect(branch.branchOrigin?.copiedMessageId).toBe(copied[1].id);
    expect(copied[1].answerBlocks).toEqual([figure]);

    await vi.waitFor(() => {
      expect(syncService.pushConversation).toHaveBeenCalledWith(expect.objectContaining({ id: BRANCH }));
      for (const message of copied) {
        expect(syncService.pushMessage).toHaveBeenCalledWith(expect.objectContaining({
          id: message.id, conversationId: BRANCH, userId: OWNER,
        }));
      }
    });
    await vi.waitFor(async () => {
      expect(await db.messageSyncQueue.count()).toBe(0);
      expect(await db.conversationSyncQueue.count()).toBe(0);
    });
  });

  it('preserves the branch after editing and deleting its source', async () => {
    await conversationRepo.branch(SOURCE, FORK, BRANCH, 'Independent branch');
    await vi.waitFor(async () => {
      expect(await db.messageSyncQueue.count()).toBe(0);
      expect(await db.conversationSyncQueue.count()).toBe(0);
    });

    await db.messages.update(FORK, { content: 'Original edited afterwards' });
    await conversationRepo.delete(SOURCE);

    expect(await conversationRepo.getById(SOURCE, OWNER)).toBeUndefined();
    expect(await conversationRepo.getById(BRANCH, OWNER)).toBeDefined();
    expect((await messageRepo.getByConversationId(BRANCH, OWNER)).map(({ content }) => content))
      .toEqual(['Earlier question', 'Selected answer']);
  });

  it('persists only one snapshot for concurrent retries with the same branch id', async () => {
    await Promise.all([
      conversationRepo.branch(SOURCE, FORK, BRANCH, 'Retry branch'),
      conversationRepo.branch(SOURCE, FORK, BRANCH, 'Retry branch'),
    ]);

    expect(await db.conversations.count()).toBe(2);
    expect(await messageRepo.getByConversationId(BRANCH, OWNER)).toHaveLength(2);
    await vi.waitFor(async () => {
      expect(await db.messageSyncQueue.count()).toBe(0);
      expect(await db.conversationSyncQueue.count()).toBe(0);
    });
  });

  it('rejects foreign sources, user-message fork points, and missing fork points without creating rows', async () => {
    vi.mocked(getCurrentUserId).mockReturnValue('different-user');
    await expect(conversationRepo.branch(SOURCE, FORK, BRANCH, 'Foreign')).rejects.toThrow();

    vi.mocked(getCurrentUserId).mockReturnValue(OWNER);
    await expect(conversationRepo.branch(SOURCE, LATER, BRANCH, 'User turn')).rejects.toThrow();
    await expect(conversationRepo.branch(SOURCE, BRANCH, BRANCH, 'Missing turn')).rejects.toThrow();

    expect(await db.conversations.get(BRANCH)).toBeUndefined();
    expect(await db.messages.count()).toBe(3);
    expect(await db.conversationSyncQueue.count()).toBe(0);
    expect(await db.messageSyncQueue.count()).toBe(0);
  });
});
