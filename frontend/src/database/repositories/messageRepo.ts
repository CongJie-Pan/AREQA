/**
 * Message Repository
 * Provides CRUD operations for message entities
 * Automatically updates conversation statistics on message operations
 * Uses atomic operations to prevent race conditions
 */

import { db } from '../db';
import type { Message } from '../schema';
import { generateUUID } from '@/utils/id';

export const messageRepo = {
  /**
   * Add a new message to a conversation
   * Automatically updates conversation statistics (messageCount, lastMessagePreview)
   * Sets conversation title from first user message
   * Uses atomic modify operation to prevent race conditions
   * @param conversationId - The conversation to add the message to
   * @param messageData - Message data (excluding id, conversationId, createdAt)
   * @returns The created message
   */
  async add(
    conversationId: string,
    messageData: Omit<Message, 'id' | 'conversationId' | 'createdAt'>
  ): Promise<Message> {
    const message: Message = {
      id: generateUUID(),
      conversationId,
      ...messageData,
      createdAt: new Date(),
    };

    await db.transaction('rw', [db.messages, db.conversations], async () => {
      // Add the message first
      await db.messages.add(message);

      // Use atomic modify operation to update conversation
      // This prevents race conditions when multiple messages are added concurrently
      await db.conversations
        .where('id')
        .equals(conversationId)
        .modify((conv) => {
          // Increment message count atomically
          conv.messageCount = (conv.messageCount || 0) + 1;
          conv.lastMessagePreview = message.content.slice(0, 100);
          conv.updatedAt = new Date();
        });
    });

    return message;
  },

  /**
   * Get all messages for a conversation ordered by creation time (ascending)
   * @param conversationId - The conversation ID
   * @returns Array of messages in chronological order
   */
  async getByConversationId(conversationId: string): Promise<Message[]> {
    return db.messages.where('conversationId').equals(conversationId).sortBy('createdAt');
  },

  /**
   * Update a message
   * @param id - The message ID
   * @param updates - Partial message data to update
   */
  async update(id: string, updates: Partial<Message>): Promise<void> {
    await db.messages.update(id, updates);
  },

  /**
   * Delete a single message
   * Automatically updates conversation statistics using atomic decrement
   * @param id - The message ID to delete
   */
  async delete(id: string): Promise<void> {
    const message = await db.messages.get(id);
    if (!message) return;

    await db.transaction('rw', [db.messages, db.conversations], async () => {
      // Delete the message first
      await db.messages.delete(id);

      // Use atomic modify to decrement message count
      // This prevents race conditions when multiple messages are deleted concurrently
      await db.conversations
        .where('id')
        .equals(message.conversationId)
        .modify((conv) => {
          conv.messageCount = Math.max(0, (conv.messageCount || 1) - 1);
          conv.updatedAt = new Date();
        });
    });
  },

  /**
   * Delete all messages for a conversation
   * Updates conversation statistics atomically
   * @param conversationId - The conversation ID
   */
  async deleteByConversationId(conversationId: string): Promise<void> {
    await db.transaction('rw', [db.messages, db.conversations], async () => {
      // Delete all messages for the conversation
      await db.messages.where('conversationId').equals(conversationId).delete();

      // Reset message count atomically
      await db.conversations
        .where('id')
        .equals(conversationId)
        .modify((conv) => {
          conv.messageCount = 0;
          conv.lastMessagePreview = '';
          conv.updatedAt = new Date();
        });
    });
  },
};
