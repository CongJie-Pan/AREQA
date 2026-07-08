/**
 * Dexie database instance
 * Provides IndexedDB access through Dexie.js wrapper
 */

import Dexie, { type EntityTable } from 'dexie';
import type { Conversation, Message, Setting } from './schema';

/**
 * PerplexityQA Database class
 * Extends Dexie to provide typed table access
 */
export function getCurrentUserId(): string {
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.includes('-auth-token')) {
        const item = localStorage.getItem(key);
        if (item) {
          const parsed = JSON.parse(item);
          if (parsed?.user?.id) {
            return parsed.user.id;
          }
        }
      }
    }
  } catch (e) {
    console.error("Failed to parse auth token", e);
  }
  return 'default_user';
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
  /** Settings table */
  settings!: EntityTable<Setting, 'key'>;

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
      const currentUserId = getCurrentUserId();
      await tx.table('conversations').toCollection().modify(conv => {
        conv.userId = conv.userId ?? currentUserId;
      });
      await tx.table('messages').toCollection().modify(msg => {
        msg.userId = msg.userId ?? currentUserId;
      });
    });

    // Handle multi-tab upgrades
    this.on('versionchange', () => {
      window.location.reload();
    });
  }
}

// Singleton instance - ensures only one database connection
export const db = new PerplexityQADatabase();
