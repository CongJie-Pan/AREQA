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
class PerplexityQADatabase extends Dexie {
  /** Conversations table */
  conversations!: EntityTable<Conversation, 'id'>;
  /** Messages table */
  messages!: EntityTable<Message, 'id'>;
  /** Settings table */
  settings!: EntityTable<Setting, 'key'>;

  constructor() {
    super('PerplexityQA');

    // Define database schema with indexed fields
    this.version(1).stores({
      // conversations: id (primary), indexed by createdAt and updatedAt
      conversations: 'id, createdAt, updatedAt',
      // messages: id (primary), indexed by conversationId, createdAt, and compound index
      messages: 'id, conversationId, createdAt, [conversationId+createdAt]',
      // settings: key (primary)
      settings: 'key',
    });
  }
}

// Singleton instance - ensures only one database connection
export const db = new PerplexityQADatabase();
