/**
 * Message Repository
 * Provides CRUD operations for message entities
 * Automatically updates conversation statistics on message operations
 * Uses atomic operations to prevent race conditions
 */

import { db, getCurrentUserId } from '../db';
import type { Message, MessageFeedback, MessageFeedbackDetails } from '../schema';
import { generateUUID } from '@/utils/id';
import { syncService } from '@/services/syncService';
import { logger } from '@/utils/logger';

type AddMessageData = Omit<Message, 'id' | 'conversationId' | 'createdAt' | 'userId'> & {
  id?: string;
  /** Preserve turn order when speech transcription completes out of order. */
  createdAt?: Date;
};

export const messageRepo = {
  /**
   * Add a new message to a conversation
   * Automatically updates conversation statistics (messageCount, lastMessagePreview)
   * Sets conversation title from first user message
   * Uses atomic modify operation to prevent race conditions
   * @param conversationId - The conversation to add the message to
   * @param messageData - Message data with optional stable id and turn timestamp.
   * @returns The created message
   */
  async add(
    conversationId: string,
    messageData: AddMessageData
  ): Promise<Message> {
    const userId = getCurrentUserId();
    if (!userId) throw new Error('Authentication required to persist messages');
    const createdAt = messageData.createdAt ?? new Date();

    const message: Message = {
      id: messageData.id ?? generateUUID(),
      userId,
      conversationId,
      ...messageData,
      createdAt,
      updatedAt: messageData.updatedAt ?? createdAt,
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
      
      if (message.role === 'user' && !messageData.citations && !messageData.searchResults && !messageData.suggestions) {
        await db.conversations.update(conversationId, {
          lastMessagePreview: message.content.substring(0, 100) + (message.content.length > 100 ? '...' : ''),
        });
      }
    });

    void Promise.resolve(syncService.pushMessage(message)).catch((error) => {
      logger.error('Message add cloud sync failed', error instanceof Error ? error : new Error(String(error)), {
        component: 'messageRepo',
        messageId: message.id,
        conversationId,
      });
    });
    
    // Also update conversation timestamp in cloud if needed
    // (though conversation update above will trigger sync if we hooked transaction, 
    // but Dexie transaction doesn't trigger hooks for us automatically here. We can just push it.)
    const conv = await db.conversations.get(conversationId);
    if (conv) {
      void syncService.pushConversation(conv);
    }

    return message;
  },

  /**
   * Get all messages for a conversation ordered by creation time (ascending)
   * @param conversationId - The conversation ID
   * @returns Array of messages in chronological order
   */
  async getByConversationId(conversationId: string, userId: string): Promise<Message[]> {
    const messages = await db.messages.where('conversationId').equals(conversationId).sortBy('createdAt');
    return messages.filter((message) => message.userId === userId);
  },

  /**
   * Update a message
   * @param id - The message ID
   * @param updates - Partial message data to update
   */
  async update(id: string, updates: Partial<Message>): Promise<void> {
    const existing = await db.messages.get(id);
    if (!existing) return;

    const updatedMessage: Message = {
      ...existing,
      ...updates,
      updatedAt: updates.updatedAt ?? new Date(),
    };

    await syncService.pushMessage(updatedMessage);
    await db.messages.put(updatedMessage);
  },

  /**
   * Update user feedback on an assistant message and sync the change to cloud.
   *
   * @param id - The assistant message ID.
   * @param feedback - New feedback value, or null to clear the feedback.
   * @throws Error when the target message is missing or is not an assistant reply.
   */
  async updateFeedback(
    id: string,
    feedback: MessageFeedback | null,
    details: MessageFeedbackDetails = {}
  ): Promise<void> {
    const message = await db.messages.get(id);
    if (!message) throw new Error('Message not found');
    if (message.role !== 'assistant') {
      throw new Error('Feedback can only be applied to assistant messages');
    }

    const feedbackUpdatedAt = feedback ? new Date() : null;
    const feedbackReason = feedback === 'disliked' ? details.reason ?? null : null;
    const feedbackComment = feedback === 'disliked' ? details.comment ?? null : null;

    await syncService.updateMessageFeedback(id, feedback, feedbackUpdatedAt, {
      reason: feedbackReason,
      comment: feedbackComment,
    });

    await db.messages.update(id, {
      feedback,
      feedbackReason,
      feedbackComment,
      feedbackUpdatedAt,
    });
  },

  /**
   * Delete a single message
   * Automatically updates conversation statistics using atomic decrement
   * @param id - The message ID to delete
   */
  async delete(id: string): Promise<void> {
    const message = await db.messages.get(id);
    if (!message) return;

    const deletion = {
      id: message.id,
      userId: message.userId,
      conversationId: message.conversationId,
      deletedAt: new Date(),
      retryCount: 0,
      lastError: null,
    };

    await db.transaction('rw', [db.messages, db.conversations, db.messageDeletions], async () => {
      // Delete the message first
      await db.messages.delete(id);
      await db.messageDeletions.put(deletion);

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

    await syncService.deleteMessage(id);
  },

  /**
   * Delete a bounded set of messages from one conversation and sync each
   * message tombstone to cloud.
   *
   * @param conversationId - Conversation that owns all target messages.
   * @param ids - Message IDs to delete. Unknown IDs are ignored.
   */
  async deleteManyByConversationId(conversationId: string, ids: string[]): Promise<void> {
    const uniqueIds = [...new Set(ids)].filter(Boolean);
    if (uniqueIds.length === 0) return;

    let deletedIds: string[] = [];
    const deletedAt = new Date();
    await db.transaction('rw', [db.messages, db.conversations, db.messageDeletions], async () => {
      const existingMessages = await db.messages
        .where('id')
        .anyOf(uniqueIds)
        .filter((message) => message.conversationId === conversationId)
        .toArray();
      deletedIds = existingMessages.map((message) => message.id);
      if (deletedIds.length === 0) return;

      await db.messages.bulkDelete(deletedIds);
      await db.messageDeletions.bulkPut(existingMessages.map((message) => ({
        id: message.id,
        userId: message.userId,
        conversationId: message.conversationId,
        deletedAt,
        retryCount: 0,
        lastError: null,
      })));

      const remainingMessages = await db.messages
        .where('conversationId')
        .equals(conversationId)
        .sortBy('createdAt');
      const latestRemainingMessage = remainingMessages.at(-1);

      await db.conversations
        .where('id')
        .equals(conversationId)
        .modify((conv) => {
          conv.messageCount = Math.max(0, (conv.messageCount || 0) - deletedIds.length);
          conv.lastMessagePreview = latestRemainingMessage?.content.slice(0, 100) ?? '';
          conv.updatedAt = new Date();
        });
    });

    await Promise.allSettled(deletedIds.map((id) => syncService.deleteMessage(id)));

    const conversation = await db.conversations.get(conversationId);
    if (conversation) {
      syncService.pushConversation(conversation);
    }
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
