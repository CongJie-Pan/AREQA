/**
 * Conversation Repository
 * Provides CRUD operations for conversation entities
 */

import { db } from '../db';
import type { Conversation } from '../schema';
import { generateUUID } from '@/utils/id';

export const conversationRepo = {
  /**
   * Create a new conversation
   * @param title - Optional conversation title (defaults to '新對話')
   * @returns The created conversation
   */
  async create(title?: string): Promise<Conversation> {
    const now = new Date();
    const conversation: Conversation = {
      id: generateUUID(),
      title: title || '新對話',
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
      lastMessagePreview: '',
    };
    await db.conversations.add(conversation);
    return conversation;
  },

  /**
   * Get all conversations ordered by update time (descending)
   * @returns Array of conversations, most recently updated first
   */
  async getAll(): Promise<Conversation[]> {
    return db.conversations
      .orderBy('updatedAt')
      .reverse()
      .toArray();
  },

  /**
   * Get a conversation by its ID
   * @param id - The conversation ID
   * @returns The conversation or undefined if not found
   */
  async getById(id: string): Promise<Conversation | undefined> {
    return db.conversations.get(id);
  },

  /**
   * Update a conversation
   * Automatically updates the updatedAt timestamp
   * @param id - The conversation ID
   * @param updates - Partial conversation data to update
   */
  async update(id: string, updates: Partial<Conversation>): Promise<void> {
    await db.conversations.update(id, {
      ...updates,
      updatedAt: new Date(),
    });
  },

  /**
   * Delete a conversation and all its associated messages
   * Uses a transaction to ensure atomicity
   * @param id - The conversation ID to delete
   */
  async delete(id: string): Promise<void> {
    await db.transaction('rw', [db.conversations, db.messages], async () => {
      await db.messages.where('conversationId').equals(id).delete();
      await db.conversations.delete(id);
    });
  },

  /**
   * Clear all conversations and messages
   * Uses a transaction to ensure atomicity
   */
  async clearAll(): Promise<void> {
    await db.transaction('rw', [db.conversations, db.messages], async () => {
      await db.messages.clear();
      await db.conversations.clear();
    });
  },
};
