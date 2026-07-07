/**
 * Conversation Repository
 * Provides CRUD operations for conversation entities
 */

import { db, getCurrentUserId } from '../db';
import type { Conversation } from '../schema';
import { generateUUID } from '@/utils/id';
import { syncService } from '@/services/syncService';

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
      userId: getCurrentUserId(),
      title: title || '新對話',
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
      lastMessagePreview: '',
    };
    await db.conversations.add(conversation);
    syncService.pushConversation(conversation);
    return conversation;
  },

  /**
   * Get all conversations ordered by update time (descending)
   * @returns Array of conversations, most recently updated first
   */
  async getAll(): Promise<Conversation[]> {
    const userId = getCurrentUserId();
    const conversations = await db.conversations
      .where('userId')
      .equals(userId)
      .sortBy('updatedAt');
    
    return conversations.reverse();
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
    const updatedAt = new Date();
    await db.conversations.update(id, {
      ...updates,
      updatedAt,
    });
    
    // Push the updated conversation to cloud (if it exists)
    const conv = await db.conversations.get(id);
    if (conv) {
      syncService.pushConversation(conv);
    }
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
    syncService.deleteConversation(id);
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
