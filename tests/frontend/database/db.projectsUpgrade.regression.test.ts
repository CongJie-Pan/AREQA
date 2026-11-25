import 'fake-indexeddb/auto';
import Dexie from '../../../frontend/node_modules/dexie';
import { describe, expect, it, vi } from 'vitest';

/**
 * Regression: the v11 (projects) schema upgrade must keep every existing row.
 * A v10 database is written with the previous schema, then the app database
 * module opens it and upgrades in place.
 */
describe('IndexedDB v10 → v11 projects upgrade', () => {
  it('keeps conversations, messages, notes and queues, and adds an empty projects table', async () => {
    await Dexie.delete('PerplexityQA');
    const legacy = new Dexie('PerplexityQA');
    legacy.version(10).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, updatedAt, [conversationId+createdAt]',
      messageDeletions: 'id, userId, conversationId, deletedAt, [userId+deletedAt]',
      messageSyncQueue: 'id, userId, conversationId, queuedAt, updatedAt, [userId+queuedAt]',
      conversationSyncQueue: 'id, userId, queuedAt, updatedAt, [userId+queuedAt]',
      settings: 'key',
      notes: 'id, userId, conversationId, messageId, createdAt, updatedAt, isPinned, *tags, [userId+createdAt], [userId+messageId], [userId+isPinned]',
    });
    const at = new Date('2026-11-20T00:00:00Z');
    await legacy.table('conversations').add({
      id: 'c1', userId: 'u', title: 'Old chat', createdAt: at, updatedAt: at, messageCount: 1, lastMessagePreview: '', kind: 'research_coach',
    });
    await legacy.table('messages').add({ id: 'm1', userId: 'u', conversationId: 'c1', role: 'user', content: 'hi', createdAt: at, updatedAt: at });
    await legacy.table('notes').add({ id: 'n1', userId: 'u', conversationId: 'c1', messageId: 'm1', contentSnapshot: 'x', tags: [], isPinned: false, createdAt: at, updatedAt: at });
    await legacy.table('conversationSyncQueue').add({ id: 'c1', userId: 'u', queuedAt: at, updatedAt: at, retryCount: 0 });
    legacy.close();

    vi.resetModules();
    const { db } = await import('@/database/db');
    await db.open();

    expect(db.verno).toBeGreaterThanOrEqual(11);
    const conversation = await db.conversations.get('c1');
    expect(conversation).toMatchObject({ title: 'Old chat', kind: 'research_coach' });
    expect(conversation?.projectId).toBeUndefined();
    expect(await db.messages.get('m1')).toMatchObject({ content: 'hi' });
    expect(await db.notes.get('n1')).toMatchObject({ contentSnapshot: 'x' });
    expect(await db.conversationSyncQueue.get('c1')).toBeDefined();
    expect(await db.projects.count()).toBe(0);
    // The new index answers project membership queries.
    expect(await db.conversations.where('projectId').equals('p1').count()).toBe(0);
    db.close();
  });
});
