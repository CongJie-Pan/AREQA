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
import { queueConversationCloudSync, scheduleConversationCloudSync } from './conversationRepo';

type AddMessageData = Omit<Message, 'id' | 'conversationId' | 'createdAt' | 'userId'> & {
  id?: string;
  /** Preserve turn order when speech transcription completes out of order. */
  createdAt?: Date;
};

export interface ConversationMessageDiagnostics {
  messageCount: number;
  userMessageCount: number;
  assistantMessageCount: number;
  pendingSyncCount: number;
  deletionMarkerCount: number;
  latestMessageUpdatedAt: Date | null;
  latestQueuedAt: Date | null;
}

const MESSAGE_SYNC_RETRY_BASE_DELAY_MS = 1_000;
const MESSAGE_SYNC_RETRY_MAX_DELAY_MS = 30_000;
const messageSyncChains = new Map<string, Promise<void>>();
const messageSyncRetryTimers = new Map<string, ReturnType<typeof setTimeout>>();

function localMessageUpdatedAt(message: Message): Date {
  return message.updatedAt ?? message.createdAt;
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return String(error);
}

function retryDelayMs(retryCount: number): number {
  return Math.min(
    MESSAGE_SYNC_RETRY_MAX_DELAY_MS,
    MESSAGE_SYNC_RETRY_BASE_DELAY_MS * Math.max(1, 2 ** Math.min(retryCount - 1, 5)),
  );
}

export async function queueMessageCloudSync(message: Message): Promise<void> {
  const existing = await db.messageSyncQueue.get(message.id);
  await db.messageSyncQueue.put({
    id: message.id,
    userId: message.userId,
    conversationId: message.conversationId,
    queuedAt: new Date(),
    updatedAt: localMessageUpdatedAt(message),
    retryCount: existing?.retryCount ?? 0,
    lastError: existing?.lastError ?? null,
  });
}

function runQueuedMessageCloudSync(id: string): Promise<void> {
  const existingTimer = messageSyncRetryTimers.get(id);
  if (existingTimer) {
    clearTimeout(existingTimer);
    messageSyncRetryTimers.delete(id);
  }

  const next = (messageSyncChains.get(id) ?? Promise.resolve())
    .catch(() => undefined)
    .then(() => flushQueuedMessageCloudSync(id));
  const tracked = next.finally(() => {
    if (messageSyncChains.get(id) === tracked) {
      messageSyncChains.delete(id);
    }
  });
  messageSyncChains.set(id, tracked);
  return tracked;
}

export function scheduleQueuedMessageCloudSync(id: string, delayMs = 0): void {
  const existingTimer = messageSyncRetryTimers.get(id);
  if (existingTimer) {
    clearTimeout(existingTimer);
    messageSyncRetryTimers.delete(id);
  }

  if (delayMs <= 0) {
    void runQueuedMessageCloudSync(id);
    return;
  }

  const timer = setTimeout(() => {
    messageSyncRetryTimers.delete(id);
    void runQueuedMessageCloudSync(id);
  }, delayMs);
  messageSyncRetryTimers.set(id, timer);
}

async function flushQueuedMessageCloudSync(id: string): Promise<void> {
  const pending = await db.messageSyncQueue.get(id);
  if (!pending) return;

  const message = await db.messages.get(id);
  if (!message) {
    await db.messageSyncQueue.delete(id);
    return;
  }

  const pushedUpdatedAt = localMessageUpdatedAt(message);
  try {
    await syncService.pushMessage(message);
    const latestPending = await db.messageSyncQueue.get(id);
    if (latestPending && latestPending.updatedAt.getTime() <= pushedUpdatedAt.getTime()) {
      await db.messageSyncQueue.delete(id);
    }
    logger.info('sync_message_queue_flushed', {
      component: 'messageRepo',
      messageId: id,
      conversationId: message.conversationId,
      retryCount: pending.retryCount,
    });
  } catch (error) {
    const nextRetryCount = pending.retryCount + 1;
    await db.messageSyncQueue.update(id, {
      retryCount: nextRetryCount,
      lastError: safeErrorMessage(error),
    });
    logger.error('sync_message_queue_push_failed', error instanceof Error ? error : new Error(safeErrorMessage(error)), {
      component: 'messageRepo',
      messageId: id,
      conversationId: message.conversationId,
      retryCount: nextRetryCount,
    });
    scheduleQueuedMessageCloudSync(id, retryDelayMs(nextRetryCount));
  }
}

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

    await db.transaction('rw', [db.messages, db.conversations, db.messageSyncQueue, db.conversationSyncQueue], async () => {
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

      const conversation = await db.conversations.get(conversationId);
      if (conversation) {
        await queueConversationCloudSync(conversation);
      }
      await queueMessageCloudSync(message);
    });

    scheduleConversationCloudSync(conversationId);
    scheduleQueuedMessageCloudSync(message.id);
    
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
   * Return safe metadata for investigating conversation-load failures.
   *
   * Compatibility:
   *   This intentionally excludes message content, prompts, model output, and
   *   attachment names. It is suitable for frontend diagnostics logs.
   */
  async getConversationDiagnostics(
    conversationId: string,
    userId: string,
  ): Promise<ConversationMessageDiagnostics> {
    const [messages, pendingRows, deletionRows] = await Promise.all([
      db.messages
        .where('conversationId')
        .equals(conversationId)
        .filter((message) => message.userId === userId)
        .toArray(),
      db.messageSyncQueue
        .where('conversationId')
        .equals(conversationId)
        .filter((row) => row.userId === userId)
        .toArray(),
      db.messageDeletions
        .where('conversationId')
        .equals(conversationId)
        .filter((row) => row.userId === userId)
        .toArray(),
    ]);

    const latestMessageUpdatedAt = messages.reduce<Date | null>((latest, message) => {
      const updatedAt = localMessageUpdatedAt(message);
      if (!latest || updatedAt.getTime() > latest.getTime()) return updatedAt;
      return latest;
    }, null);
    const latestQueuedAt = pendingRows.reduce<Date | null>((latest, row) => {
      if (!latest || row.queuedAt.getTime() > latest.getTime()) return row.queuedAt;
      return latest;
    }, null);

    return {
      messageCount: messages.length,
      userMessageCount: messages.filter((message) => message.role === 'user').length,
      assistantMessageCount: messages.filter((message) => message.role === 'assistant').length,
      pendingSyncCount: pendingRows.length,
      deletionMarkerCount: deletionRows.length,
      latestMessageUpdatedAt,
      latestQueuedAt,
    };
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

    await db.transaction('rw', [db.messages, db.messageSyncQueue], async () => {
      await db.messages.put(updatedMessage);
      await queueMessageCloudSync(updatedMessage);
    });
    scheduleQueuedMessageCloudSync(id);
  },

  /**
   * Flush pending message cloud sync rows for the current user.
   *
   * Side Effects:
   *   Starts per-message serialized cloud push workers. The method resolves
   *   after the currently scheduled attempts settle, while failed rows remain
   *   queued with retry metadata for later automatic attempts.
   */
  async flushPendingCloudSync(userId = getCurrentUserId()): Promise<void> {
    if (!userId || userId === 'default_user') return;

    const pendingRows = await db.messageSyncQueue
      .where('userId')
      .equals(userId)
      .sortBy('queuedAt');

    await Promise.allSettled(
      pendingRows.map((row) => runQueuedMessageCloudSync(row.id)),
    );
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

    await db.transaction('rw', [db.messages, db.conversations, db.messageDeletions, db.messageSyncQueue, db.conversationSyncQueue], async () => {
      // Delete the message first
      await db.messages.delete(id);
      await db.messageDeletions.put(deletion);
      await db.messageSyncQueue.delete(id);

      // Use atomic modify to decrement message count
      // This prevents race conditions when multiple messages are deleted concurrently
      await db.conversations
        .where('id')
        .equals(message.conversationId)
        .modify((conv) => {
          conv.messageCount = Math.max(0, (conv.messageCount || 1) - 1);
          conv.updatedAt = new Date();
        });
      const conversation = await db.conversations.get(message.conversationId);
      if (conversation) {
        await queueConversationCloudSync(conversation);
      }
    });

    scheduleConversationCloudSync(message.conversationId);
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
    await db.transaction('rw', [db.messages, db.conversations, db.messageDeletions, db.messageSyncQueue, db.conversationSyncQueue], async () => {
      const existingMessages = await db.messages
        .where('id')
        .anyOf(uniqueIds)
        .filter((message) => message.conversationId === conversationId)
        .toArray();
      deletedIds = existingMessages.map((message) => message.id);
      if (deletedIds.length === 0) return;

      await db.messages.bulkDelete(deletedIds);
      await db.messageSyncQueue.bulkDelete(deletedIds);
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
      const conversation = await db.conversations.get(conversationId);
      if (conversation) {
        await queueConversationCloudSync(conversation);
      }
    });

    scheduleConversationCloudSync(conversationId);
    await Promise.allSettled(deletedIds.map((id) => syncService.deleteMessage(id)));

  },

  /**
   * Delete all messages for a conversation
   * Updates conversation statistics atomically
   * @param conversationId - The conversation ID
   */
  async deleteByConversationId(conversationId: string): Promise<void> {
    await db.transaction('rw', [db.messages, db.conversations, db.messageSyncQueue, db.conversationSyncQueue], async () => {
      const deletedIds = (await db.messages.where('conversationId').equals(conversationId).primaryKeys()) as string[];
      // Delete all messages for the conversation
      await db.messages.where('conversationId').equals(conversationId).delete();
      if (deletedIds.length > 0) {
        await db.messageSyncQueue.bulkDelete(deletedIds);
      }

      // Reset message count atomically
      await db.conversations
        .where('id')
        .equals(conversationId)
        .modify((conv) => {
          conv.messageCount = 0;
          conv.lastMessagePreview = '';
          conv.updatedAt = new Date();
        });
      const conversation = await db.conversations.get(conversationId);
      if (conversation) {
        await queueConversationCloudSync(conversation);
      }
    });

    scheduleConversationCloudSync(conversationId);
  },
};
