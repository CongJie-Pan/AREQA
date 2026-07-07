import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import Dexie from 'dexie';
import 'fake-indexeddb/auto';

// Mock localStorage for getCurrentUserId
const localStorageMock = (function () {
  let store: Record<string, string> = {};
  return {
    getItem: function (key: string) {
      return store[key] || null;
    },
    setItem: function (key: string, value: string) {
      store[key] = value.toString();
    },
    clear: function () {
      store = {};
    },
    key: function(i: number) {
      return Object.keys(store)[i];
    },
    get length() {
      return Object.keys(store).length;
    }
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

describe('Dexie Database Upgrade (Version 1 to 2)', () => {
  beforeEach(async () => {
    // Clear localStorage
    window.localStorage.clear();
    
    // Create a Version 1 database and insert old data (without userId)
    const db1 = new Dexie('PerplexityQA_Test');
    db1.version(1).stores({
      conversations: 'id, createdAt, updatedAt',
      messages: 'id, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
    });
    
    await db1.open();
    
    // Insert legacy data (no userId)
    await db1.table('conversations').add({
      id: 'conv_1',
      title: 'Old Conversation',
      createdAt: Date.now(),
      updatedAt: Date.now()
    });
    
    await db1.table('messages').add({
      id: 'msg_1',
      conversationId: 'conv_1',
      role: 'user',
      content: 'Hello',
      createdAt: Date.now()
    });
    
    db1.close();
  });

  afterEach(async () => {
    await Dexie.delete('PerplexityQA_Test');
    vi.restoreAllMocks();
  });

  it('should backfill userId during upgrade from v1 to v2', async () => {
    // Simulate user being logged in by mocking localStorage token
    window.localStorage.setItem('supabase-auth-token', JSON.stringify({
      user: { id: 'user_999' }
    }));

    // Function matching getCurrentUserId from db.ts
    function getCurrentUserId(): string {
      try {
        for (let i = 0; i < window.localStorage.length; i++) {
          const key = window.localStorage.key(i);
          if (key && key.includes('-auth-token')) {
            const item = window.localStorage.getItem(key);
            if (item) {
              const parsed = JSON.parse(item);
              if (parsed?.user?.id) {
                return parsed.user.id;
              }
            }
          }
        }
      } catch (e) {}
      return 'default_user';
    }

    // Now instantiate Version 2 to trigger the upgrade
    const db2 = new Dexie('PerplexityQA_Test');
    db2.version(1).stores({
      conversations: 'id, createdAt, updatedAt',
      messages: 'id, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
    });

    db2.version(2).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
    }).upgrade(async tx => {
      const currentUserId = getCurrentUserId();
      await tx.table('conversations').toCollection().modify((conv: any) => {
        conv.userId = conv.userId ?? currentUserId;
      });
      await tx.table('messages').toCollection().modify((msg: any) => {
        msg.userId = msg.userId ?? currentUserId;
      });
    });

    await db2.open();

    // Verify conversations table
    const convs = await db2.table('conversations').toArray();
    expect(convs).toHaveLength(1);
    expect(convs[0].userId).toBe('user_999');

    // Verify messages table
    const msgs = await db2.table('messages').toArray();
    expect(msgs).toHaveLength(1);
    expect(msgs[0].userId).toBe('user_999');
    
    db2.close();
  });
});
