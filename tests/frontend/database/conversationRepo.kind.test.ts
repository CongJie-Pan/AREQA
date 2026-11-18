import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { db, getCurrentUserId } from '@/database/db';
import { conversationRepo } from '@/database/repositories/conversationRepo';
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

const OWNER = 'kind-owner';
const SOURCE = '8f0c2c55-1d3e-4c11-9a77-1b0e4c2f9a10';
const BRANCH = 'f3a1d6e2-5b8c-4a8e-9a1f-2c3d4e5f6a7b';
const FORK = '0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d';

async function seedSource(kind?: 'research_coach') {
  const now = new Date(2026, 10, 18);
  await db.conversations.add({
    id: SOURCE, userId: OWNER, title: 'Source', createdAt: now, updatedAt: now,
    messageCount: 2, lastMessagePreview: '', ...(kind ? { kind } : {}),
  });
  await db.messages.bulkAdd([
    { id: '11111111-1111-4111-8111-111111111111', userId: OWNER, conversationId: SOURCE, role: 'user', content: 'pain point', createdAt: new Date(2026, 10, 18, 0, 0, 1) },
    { id: FORK, userId: OWNER, conversationId: SOURCE, role: 'assistant', content: 'candidate topics', createdAt: new Date(2026, 10, 18, 0, 0, 2) },
  ]);
}

describe('Conversation kind persistence', () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue(OWNER);
    vi.mocked(syncService.pushConversation).mockResolvedValue(true);
    await db.open();
    await db.conversationSyncQueue.clear();
    await db.messageSyncQueue.clear();
    await db.conversations.clear();
    await db.messages.clear();
  });

  it('creates chat conversations without a kind and Topic Finder ones with it', async () => {
    const chat = await conversationRepo.create();
    const coach = await conversationRepo.create(undefined, 'research_coach');

    expect(chat.kind).toBeUndefined();
    expect((await db.conversations.get(chat.id))?.kind).toBeUndefined();
    expect(coach.kind).toBe('research_coach');
    expect((await db.conversations.get(coach.id))?.kind).toBe('research_coach');
  });

  it('keeps a Topic Finder branch in the Topic Finder workspace', async () => {
    await seedSource('research_coach');

    const branch = await conversationRepo.branch(SOURCE, FORK, BRANCH, 'Branch');

    expect(branch.kind).toBe('research_coach');
    expect((await db.conversations.get(BRANCH))?.kind).toBe('research_coach');
  });

  it('keeps a chat branch in the chat workspace', async () => {
    await seedSource();

    const branch = await conversationRepo.branch(SOURCE, FORK, BRANCH, 'Branch');

    expect(branch.kind).toBeUndefined();
  });
});
