/**
 * Dexie database instance
 * Provides IndexedDB access through Dexie.js wrapper
 */

import Dexie, { type EntityTable } from 'dexie';
import type {
  Conversation,
  ConversationSyncQueueItem,
  Message,
  MessageDeletion,
  MessageSyncQueueItem,
  Note,
  Setting,
} from './schema';

/**
 * PerplexityQA Database class
 * Extends Dexie to provide typed table access
 */
export function getCurrentUserId(): string | null {
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.includes('-auth-token')) {
        const item = localStorage.getItem(key);
        if (item) {
          const parsed = JSON.parse(item);
          const isExpired = parsed?.expires_at && parsed.expires_at <= Math.floor(Date.now() / 1000);
          if (!isExpired && parsed?.user?.id) {
            return parsed.user.id;
          }
        }
      }
    }
  } catch (e) {
    console.error("Failed to parse auth token", e);
  }
  return null;
}

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.includes('-auth-token')) {
        const item = localStorage.getItem(key);
        if (item) {
          const parsed = JSON.parse(item);
          if (parsed?.access_token) {
            return parsed.access_token;
          }
        }
      }
    }
  } catch (e) {
    console.error("Failed to parse auth token", e);
  }
  return null;
}

class PerplexityQADatabase extends Dexie {
  /** Conversations table */
  conversations!: EntityTable<Conversation, 'id'>;
  /** Messages table */
  messages!: EntityTable<Message, 'id'>;
  /** Local-only message delete markers used to prevent stale sync resurrection. */
  messageDeletions!: EntityTable<MessageDeletion, 'id'>;
  /** Local-only pending message cloud sync queue. */
  messageSyncQueue!: EntityTable<MessageSyncQueueItem, 'id'>;
  /** Local-only pending conversation cloud sync queue. */
  conversationSyncQueue!: EntityTable<ConversationSyncQueueItem, 'id'>;
  /** Settings table */
  settings!: EntityTable<Setting, 'key'>;
  /** Notes table */
  notes!: EntityTable<Note, 'id'>;

  constructor() {
    super('PerplexityQA');

    // Define database schema with indexed fields (Version 1)
    this.version(1).stores({
      conversations: 'id, createdAt, updatedAt',
      messages: 'id, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
    });

    // Version 2: Multi-tenant support with userId
    this.version(2).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
    }).upgrade(async tx => {
      const currentUserId = getCurrentUserId() ?? 'default_user';
      await tx.table('conversations').toCollection().modify(conv => {
        conv.userId = conv.userId ?? currentUserId;
      });
      await tx.table('messages').toCollection().modify(msg => {
        msg.userId = msg.userId ?? currentUserId;
      });
    });

    // Version 3: Assistant message feedback is stored on the message row.
    this.version(3).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
    });

    // Version 4: Structured illustrated answer blocks are stored on messages.
    this.version(4).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
    });

    // Version 5: User-saved notes linked to assistant messages.
    this.version(5).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
      notes: 'id, userId, conversationId, messageId, createdAt, updatedAt, [userId+createdAt], [userId+messageId]',
    });

    // Version 6: Note organization metadata for pinned notes and manual tags.
    this.version(6).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, [conversationId+createdAt]',
      settings: 'key',
      notes: 'id, userId, conversationId, messageId, createdAt, updatedAt, isPinned, *tags, [userId+createdAt], [userId+messageId], [userId+isPinned]',
    }).upgrade(async tx => {
      await tx.table('notes').toCollection().modify(note => {
        note.tags = Array.isArray(note.tags) ? note.tags : [];
        note.isPinned = Boolean(note.isPinned);
      });
    });

    // Version 7: Local message tombstones prevent stale cloud pull snapshots
    // from resurrecting user-deleted turns before Supabase delete settles.
    this.version(7).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, [conversationId+createdAt]',
      messageDeletions: 'id, userId, conversationId, deletedAt, [userId+deletedAt]',
      settings: 'key',
      notes: 'id, userId, conversationId, messageId, createdAt, updatedAt, isPinned, *tags, [userId+createdAt], [userId+messageId], [userId+isPinned]',
    });

    // Version 8: Message edits need a durable clock so cloud pulls do not
    // overwrite newer local edits with stale rows from another device.
    this.version(8).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, updatedAt, [conversationId+createdAt]',
      messageDeletions: 'id, userId, conversationId, deletedAt, [userId+deletedAt]',
      settings: 'key',
      notes: 'id, userId, conversationId, messageId, createdAt, updatedAt, isPinned, *tags, [userId+createdAt], [userId+messageId], [userId+isPinned]',
    }).upgrade(async tx => {
      await tx.table('messages').toCollection().modify(message => {
        message.updatedAt = message.updatedAt ?? message.createdAt ?? new Date();
      });
    });

    // Version 9: Durable pending message sync rows let local edits survive
    // transient cloud failures and app reloads without replaying stale content.
    this.version(9).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, updatedAt, [conversationId+createdAt]',
      messageDeletions: 'id, userId, conversationId, deletedAt, [userId+deletedAt]',
      messageSyncQueue: 'id, userId, conversationId, queuedAt, updatedAt, [userId+queuedAt]',
      settings: 'key',
      notes: 'id, userId, conversationId, messageId, createdAt, updatedAt, isPinned, *tags, [userId+createdAt], [userId+messageId], [userId+isPinned]',
    });

    // Version 10: Durable pending conversation sync rows ensure a newly
    // created conversation shell/title survives reloads until cloud confirms it.
    this.version(10).stores({
      conversations: 'id, userId, createdAt, updatedAt',
      messages: 'id, userId, conversationId, createdAt, updatedAt, [conversationId+createdAt]',
      messageDeletions: 'id, userId, conversationId, deletedAt, [userId+deletedAt]',
      messageSyncQueue: 'id, userId, conversationId, queuedAt, updatedAt, [userId+queuedAt]',
      conversationSyncQueue: 'id, userId, queuedAt, updatedAt, [userId+queuedAt]',
      settings: 'key',
      notes: 'id, userId, conversationId, messageId, createdAt, updatedAt, isPinned, *tags, [userId+createdAt], [userId+messageId], [userId+isPinned]',
    });

    // Handle multi-tab upgrades
    this.on('versionchange', () => {
      window.location.reload();
    });
  }
}

// Singleton instance - ensures only one database connection
export const db = new PerplexityQADatabase();
