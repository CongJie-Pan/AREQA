/**
 * Conversation Repository
 * Provides CRUD operations for conversation entities
 */

import { db, getCurrentUserId } from '../db';
import type { Conversation } from '../schema';
import { generateUUID } from '@/utils/id';
import { syncService } from '@/services/syncService';
import { logger } from '@/utils/logger';
import { persistentAnswerBlocks } from '@/utils/answerBlocks';
import { queueMessageCloudSync, scheduleQueuedMessageCloudSync } from './messageRepo';

const CONVERSATION_SYNC_RETRY_BASE_DELAY_MS = 1_000;
const CONVERSATION_SYNC_RETRY_MAX_DELAY_MS = 30_000;
const conversationSyncChains = new Map<string, Promise<void>>();
const conversationSyncRetryTimers = new Map<string, ReturnType<typeof setTimeout>>();

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
    CONVERSATION_SYNC_RETRY_MAX_DELAY_MS,
    CONVERSATION_SYNC_RETRY_BASE_DELAY_MS * Math.max(1, 2 ** Math.min(retryCount - 1, 5)),
  );
}

export async function queueConversationCloudSync(conversation: Conversation): Promise<void> {
  const existing = await db.conversationSyncQueue.get(conversation.id);
  await db.conversationSyncQueue.put({
    id: conversation.id,
    userId: conversation.userId,
    queuedAt: new Date(),
    updatedAt: conversation.updatedAt,
    retryCount: existing?.retryCount ?? 0,
    lastError: existing?.lastError ?? null,
  });
}

function runQueuedConversationCloudSync(id: string): Promise<void> {
  const existingTimer = conversationSyncRetryTimers.get(id);
  if (existingTimer) {
    clearTimeout(existingTimer);
    conversationSyncRetryTimers.delete(id);
  }

  const next = (conversationSyncChains.get(id) ?? Promise.resolve())
    .catch(() => undefined)
    .then(() => flushQueuedConversationCloudSync(id));
  const tracked = next.finally(() => {
    if (conversationSyncChains.get(id) === tracked) {
      conversationSyncChains.delete(id);
    }
  });
  conversationSyncChains.set(id, tracked);
  return tracked;
}

export function scheduleConversationCloudSync(id: string, delayMs = 0): void {
  const existingTimer = conversationSyncRetryTimers.get(id);
  if (existingTimer) {
    clearTimeout(existingTimer);
    conversationSyncRetryTimers.delete(id);
  }

  if (delayMs <= 0) {
    void runQueuedConversationCloudSync(id);
    return;
  }

  const timer = setTimeout(() => {
    conversationSyncRetryTimers.delete(id);
    void runQueuedConversationCloudSync(id);
  }, delayMs);
  conversationSyncRetryTimers.set(id, timer);
}

async function flushQueuedConversationCloudSync(id: string): Promise<void> {
  const pending = await db.conversationSyncQueue.get(id);
  if (!pending) return;

  const conversation = await db.conversations.get(id);
  if (!conversation) {
    await db.conversationSyncQueue.delete(id);
    return;
  }

  const pushedUpdatedAt = conversation.updatedAt;
  try {
    const acknowledged = await syncService.pushConversation(conversation);
    if (!acknowledged) {
      throw new Error('Cloud conversation push was not acknowledged');
    }
    const latestPending = await db.conversationSyncQueue.get(id);
    if (latestPending && latestPending.updatedAt.getTime() <= pushedUpdatedAt.getTime()) {
      await db.conversationSyncQueue.delete(id);
    }
    logger.info('sync_conversation_queue_flushed', {
      component: 'conversationRepo',
      conversationId: id,
      retryCount: pending.retryCount,
    });
  } catch (error) {
    const nextRetryCount = pending.retryCount + 1;
    await db.conversationSyncQueue.update(id, {
      retryCount: nextRetryCount,
      lastError: safeErrorMessage(error),
    });
    logger.error('sync_conversation_queue_push_failed', error instanceof Error ? error : new Error(safeErrorMessage(error)), {
      component: 'conversationRepo',
      conversationId: id,
      retryCount: nextRetryCount,
    });
    scheduleConversationCloudSync(id, retryDelayMs(nextRetryCount));
  }
}

export const conversationRepo = {
  async branch(sourceId: string, forkMessageId: string, branchId: string, title: string): Promise<Conversation> {
    const userId = getCurrentUserId();
    if (!userId) throw new Error('Authentication required to create a branch');

    const { conversation, messageIds } = await db.transaction(
      'rw', [db.conversations, db.messages, db.conversationSyncQueue, db.messageSyncQueue],
      async () => {
        const existing = await db.conversations.get(branchId);
        if (existing) {
          if (existing.userId !== userId || existing.branchOrigin?.conversationId !== sourceId
            || existing.branchOrigin.messageId !== forkMessageId) {
            throw new Error('Branch identifier is already in use');
          }
          return { conversation: existing, messageIds: [] };
        }

        const source = await db.conversations.get(sourceId);
        if (source?.userId !== userId) throw new Error('Conversation is unavailable');
        const messages = await db.messages.where('conversationId').equals(sourceId)
          .filter((message) => message.userId === userId).sortBy('createdAt');
        const boundary = messages.findIndex((message) => message.id === forkMessageId);
        const anchor = messages[boundary];
        if (anchor?.role !== 'assistant'
          || (!anchor.content.trim() && !persistentAnswerBlocks(anchor.answerBlocks)?.length)
          || anchor.answerBlocks?.some((block) => block.type === 'image_block' && block.status === 'pending')) {
          throw new Error('Select a completed reply to branch');
        }

        const now = new Date();
        const prefix = messages.slice(0, boundary + 1).map((message, index) => ({
          ...message,
          id: generateUUID(),
          conversationId: branchId,
          // IndexedDB and cloud hydration both sort by creation time.
          createdAt: new Date(now.getTime() - boundary + index - 1),
          updatedAt: now,
          answerBlocks: persistentAnswerBlocks(message.answerBlocks),
          attachmentSourceId: message.attachments?.length ? message.attachmentSourceId ?? message.id : undefined,
          feedback: null,
          feedbackReason: null,
          feedbackComment: null,
          feedbackUpdatedAt: null,
        }));
        const conversation: Conversation = {
          id: branchId, userId, title, createdAt: now, updatedAt: now,
          messageCount: prefix.length, lastMessagePreview: anchor.content.slice(0, 100),
          branchOrigin: { conversationId: sourceId, messageId: forkMessageId, title: source.title, copiedMessageId: prefix[boundary].id },
        };
        await db.conversations.add(conversation);
        await db.messages.bulkAdd(prefix);
        await queueConversationCloudSync(conversation);
        await Promise.all(prefix.map(queueMessageCloudSync));
        return { conversation, messageIds: prefix.map((message) => message.id) };
      },
    );
    scheduleConversationCloudSync(conversation.id);
    messageIds.forEach((id) => scheduleQueuedMessageCloudSync(id));
    return conversation;
  },

  /**
   * Create a new conversation
   * @param title - Optional conversation title (defaults to '新對話')
   * @returns The created conversation
   */
  async create(title?: string): Promise<Conversation> {
    const userId = getCurrentUserId();
    if (!userId) throw new Error('Authentication required to persist conversations');

    const now = new Date();
    const conversation: Conversation = {
      id: generateUUID(),
      userId,
      title: title || '新對話',
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
      lastMessagePreview: '',
    };
    await db.transaction('rw', [db.conversations, db.conversationSyncQueue], async () => {
      await db.conversations.add(conversation);
      await queueConversationCloudSync(conversation);
    });
    scheduleConversationCloudSync(conversation.id);
    return conversation;
  },

  /**
   * Get all conversations ordered by update time (descending)
   * @returns Array of conversations, most recently updated first
   */
  async getAll(userId: string): Promise<Conversation[]> {
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
  async getById(id: string, userId: string): Promise<Conversation | undefined> {
    const conversation = await db.conversations.get(id);
    return conversation?.userId === userId ? conversation : undefined;
  },

  /**
   * Update a conversation
   * Automatically updates the updatedAt timestamp
   * @param id - The conversation ID
   * @param updates - Partial conversation data to update
   */
  async update(id: string, updates: Partial<Conversation>): Promise<void> {
    const updatedAt = new Date();
    await db.transaction('rw', [db.conversations, db.conversationSyncQueue], async () => {
      await db.conversations.update(id, {
        ...updates,
        updatedAt,
      });
      const conv = await db.conversations.get(id);
      if (conv) {
        await queueConversationCloudSync(conv);
      }
    });

    scheduleConversationCloudSync(id);
  },

  /**
   * Delete a conversation and all its associated messages
   * Uses a transaction to ensure atomicity
   * @param id - The conversation ID to delete
   */
  async delete(id: string): Promise<void> {
    await db.transaction('rw', [db.conversations, db.messages, db.conversationSyncQueue], async () => {
      await db.messages.where('conversationId').equals(id).delete();
      await db.conversationSyncQueue.delete(id);
      await db.conversations.delete(id);
    });
    syncService.deleteConversation(id);
  },

  /**
   * Clear all conversations and messages
   * Uses a transaction to ensure atomicity
   */
  async clearAll(): Promise<void> {
    await db.transaction('rw', [db.conversations, db.messages, db.conversationSyncQueue], async () => {
      await db.messages.clear();
      await db.conversations.clear();
      await db.conversationSyncQueue.clear();
    });
  },

  /** Remove legacy guest records without affecting authenticated users. */
  async clearGuestData(): Promise<void> {
    await db.transaction('rw', [db.conversations, db.messages, db.conversationSyncQueue], async () => {
      await db.messages.where('userId').equals('default_user').delete();
      await db.conversations.where('userId').equals('default_user').delete();
      await db.conversationSyncQueue.where('userId').equals('default_user').delete();
    });
  },

  /**
   * Flush pending conversation cloud sync rows for the current user.
   *
   * Side Effects:
   *   Starts per-conversation serialized cloud push workers. Failed rows stay
   *   queued with retry metadata and will be attempted later.
   */
  async flushPendingCloudSync(userId = getCurrentUserId()): Promise<void> {
    if (!userId || userId === 'default_user') return;

    const pendingRows = await db.conversationSyncQueue
      .where('userId')
      .equals(userId)
      .sortBy('queuedAt');

    await Promise.allSettled(
      pendingRows.map((row) => runQueuedConversationCloudSync(row.id)),
    );
  },
};
