import 'fake-indexeddb/auto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { db } from '@/database/db';
import { messageRepo } from '@/database/repositories/messageRepo';
import { syncService } from '@/services/syncService';
import { logger } from '@/utils/logger';

const cloud = vi.hoisted(() => ({
  rows: [] as Record<string, unknown>[],
  failId: '',
  deletes: [] as string[],
  beforeMessageRead: undefined as (() => Promise<void>) | undefined,
}));

vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: () => 'research-user',
}));

vi.mock('@/utils/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: (table: string) => ({
      select: () => ({
        eq: async () => {
          const snapshot = table === 'messages' ? [...cloud.rows] : [];
          if (table === 'messages') await cloud.beforeMessageRead?.();
          return { data: snapshot, error: null };
        },
      }),
      upsert: async () => ({ error: null }),
      delete: () => ({
        eq: (_column: string, id: string) => ({
          eq: async () => {
            cloud.deletes.push(id);
            if (id === cloud.failId) {
              return { error: { message: 'Injected delete failure', status: 503 } };
            }
            cloud.rows = cloud.rows.filter((row) => row.id !== id);
            return { error: null };
          },
        }),
      }),
    }),
  },
}));

describe('deletion research: local/cloud consistency', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    cloud.failId = '';
    cloud.deletes = [];
    cloud.beforeMessageRead = undefined;
    cloud.rows = ['user', 'assistant'].map((role, index) => ({
      id: `research-${role}`,
      user_id: 'research-user',
      conversation_id: 'research-conversation',
      role,
      content: `Synthetic ${role}`,
      created_at: new Date(1000 + index).toISOString(),
    }));
    await db.open();
    await db.messages.clear();
    await db.messageDeletions.clear();
    await db.conversations.clear();
    await db.notes.clear();
    await syncService.pullFromCloud();
  });

  afterEach(async () => {
    await db.messages.clear();
    await db.messageDeletions.clear();
    await db.conversations.clear();
    await db.notes.clear();
  });

  it('keeps a locally deleted query hidden when one cloud delete returns an error', async () => {
    cloud.failId = 'research-user';
    await messageRepo.deleteManyByConversationId(
      'research-conversation', ['research-user', 'research-assistant'],
    );
    expect(await db.messages.count()).toBe(0);
    expect([...cloud.deletes].sort()).toEqual(['research-assistant', 'research-user']);
    expect(logger.error).toHaveBeenCalledWith(
      'Delete message error',
      expect.any(Error),
      expect.objectContaining({
        component: 'syncService',
        messageId: 'research-user',
      }),
    );

    await syncService.pullFromCloud();
    expect(await db.messages.count()).toBe(0);
    expect((await db.messageDeletions.toArray()).map((row) => row.id).sort()).toEqual([
      'research-assistant',
      'research-user',
    ]);
  });

  it('does not restore deleted messages from an in-flight cloud snapshot', async () => {
    let releaseRead!: () => void;
    let markRead!: () => void;
    const readStarted = new Promise<void>((resolve) => { markRead = resolve; });
    const readReleased = new Promise<void>((resolve) => { releaseRead = resolve; });
    cloud.beforeMessageRead = async () => {
      markRead();
      await readReleased;
    };
    const pull = syncService.pullFromCloud();
    await readStarted;
    try {
      await messageRepo.deleteManyByConversationId(
        'research-conversation', ['research-user', 'research-assistant'],
      );
      expect(cloud.rows).toHaveLength(0);
      expect(await db.messages.count()).toBe(0);
    } finally {
      releaseRead();
      await pull;
    }
    expect(await db.messages.count()).toBe(0);
    cloud.beforeMessageRead = undefined;
    await syncService.pullFromCloud();
    expect(await db.messages.count()).toBe(0);
  });

  it('retains local messages deleted by another device', async () => {
    cloud.rows = [];
    await syncService.pullFromCloud();
    expect(await db.messages.count()).toBe(2);
  });
});
