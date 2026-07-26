import { db, getCurrentUserId } from '@/database/db';
import { supabase } from '@/lib/supabase';
import type { Conversation, Message } from '@/database/schema';
import { logger } from '@/utils/logger';
import { useAuthStore } from '@/store/auth';
import { normalizeAttachmentMetadata } from '@/utils/attachments';
import type { MessageFeedback } from '@/database/schema';

function handleAuthError(error: unknown): void {
  if ((error as { status?: number } | null)?.status === 401) {
    void useAuthStore.getState().invalidateSession();
  }
}

function normalizeMessageFeedback(value: unknown): MessageFeedback | null {
  return value === 'liked' || value === 'disliked' ? value : null;
}

export const syncService = {
  /**
   * Pulls all conversations and messages from Supabase for the current user
   * and merges them into the local Dexie DB.
   */
  async pullFromCloud(overrideUserId?: string) {
    const userId = overrideUserId || getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      // Pull conversations
      const { data: cloudConvs, error: convError } = await supabase
        .from('conversations')
        .select('*')
        .eq('user_id', userId);
        
      if (convError) {
        handleAuthError(convError);
        throw convError;
      }

      // Pull messages
      const { data: cloudMsgs, error: msgError } = await supabase
        .from('messages')
        .select('*')
        .eq('user_id', userId);

      if (msgError) {
        handleAuthError(msgError);
        throw msgError;
      }

      let dataChanged = false;

      // Group messages by conversation ID to calculate message count
      const msgCountByConv: Record<string, number> = {};
      if (cloudMsgs && cloudMsgs.length > 0) {
        cloudMsgs.forEach(m => {
          msgCountByConv[m.conversation_id] = (msgCountByConv[m.conversation_id] || 0) + 1;
        });
      }

      if (cloudConvs && cloudConvs.length > 0) {
        const localConvs = await db.conversations.toArray();
        const localConvMap = new Map(localConvs.map(c => [c.id, c]));
        
        const convsToUpsert = [];
        for (const c of cloudConvs) {
          const cloudDate = new Date(c.updated_at);
          const localConv = localConvMap.get(c.id);
          if (!localConv || localConv.updatedAt.getTime() < cloudDate.getTime()) {
            convsToUpsert.push({
              id: c.id,
              userId: c.user_id,
              title: c.title,
              createdAt: new Date(c.created_at),
              updatedAt: cloudDate,
              messageCount: msgCountByConv[c.id] || 0,
              lastMessagePreview: '' 
            } as Conversation);
          }
        }

        if (convsToUpsert.length > 0) {
          await db.conversations.bulkPut(convsToUpsert);
          dataChanged = true;
        }
      }

      if (cloudMsgs && cloudMsgs.length > 0) {
        const localMsgs = await db.messages.toArray();
        const localMsgMap = new Map(localMsgs.map(m => [m.id, m]));
        
        const msgsToUpsert = [];
        for (const m of cloudMsgs) {
          const cloudFeedback = normalizeMessageFeedback(m.feedback);
          const cloudFeedbackUpdatedAt = m.feedback_updated_at
            ? new Date(m.feedback_updated_at)
            : null;
          const localMsg = localMsgMap.get(m.id);

          if (
            !localMsg ||
            (localMsg.feedback ?? null) !== cloudFeedback ||
            (localMsg.feedbackUpdatedAt?.getTime() ?? null) !==
              (cloudFeedbackUpdatedAt?.getTime() ?? null)
          ) {
            msgsToUpsert.push({
              id: m.id,
              userId: m.user_id,
              conversationId: m.conversation_id,
              role: m.role,
              content: m.content,
              attachments: normalizeAttachmentMetadata(m.attachments),
              feedback: cloudFeedback,
              feedbackUpdatedAt: cloudFeedbackUpdatedAt,
              createdAt: new Date(m.created_at)
            } as Message);
          }
        }

        if (msgsToUpsert.length > 0) {
          await db.messages.bulkPut(msgsToUpsert);
          dataChanged = true;
        }
      }

      // Only reload if we actually pulled new data, and add a small delay to ensure session is stored
      if (dataChanged) {
        setTimeout(() => {
          window.location.reload();
        }, 500);
      }
    } catch (e) {
      handleAuthError(e);
      logger.error('Failed to sync from cloud', e instanceof Error ? e : new Error(String(e)));
    }
  },

  /**
   * Pushes a conversation to Supabase
   */
  async pushConversation(conv: Conversation) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      await supabase.from('conversations').upsert({
        id: conv.id,
        user_id: conv.userId,
        title: conv.title,
        created_at: conv.createdAt.toISOString(),
        updated_at: conv.updatedAt.toISOString(),
      });
    } catch (e) {
      handleAuthError(e);
      logger.error('Push conversation error', e instanceof Error ? e : new Error(String(e)));
    }
  },

  /**
   * Pushes a message to Supabase
   */
  async pushMessage(msg: Message) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      await supabase.from('messages').upsert({
        id: msg.id,
        user_id: msg.userId,
        conversation_id: msg.conversationId,
        role: msg.role,
        content: msg.content,
        attachments: normalizeAttachmentMetadata(msg.attachments),
        feedback: msg.feedback ?? null,
        feedback_updated_at: msg.feedbackUpdatedAt?.toISOString() ?? null,
        created_at: msg.createdAt.toISOString(),
      });
    } catch (e) {
      handleAuthError(e);
      logger.error('Push message error', e instanceof Error ? e : new Error(String(e)));
    }
  },

  /**
   * Updates only the assistant-feedback fields for an existing cloud message.
   */
  async updateMessageFeedback(
    messageId: string,
    feedback: MessageFeedback | null,
    feedbackUpdatedAt: Date | null
  ) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      const { data, error } = await supabase
        .from('messages')
        .update({
          feedback,
          feedback_updated_at: feedbackUpdatedAt?.toISOString() ?? null,
        })
        .eq('id', messageId)
        .eq('user_id', userId)
        .select('id');

      if (error) {
        handleAuthError(error);
        throw error;
      }

      if (!data || data.length === 0) {
        throw new Error('Cloud message not found for feedback update');
      }
    } catch (e) {
      handleAuthError(e);
      logger.error('Update message feedback error', e instanceof Error ? e : new Error(String(e)));
      throw e;
    }
  },

  /**
   * Deletes a conversation from Supabase
   */
  async deleteConversation(id: string) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      await supabase.from('conversations').delete().eq('id', id);
      await supabase.from('messages').delete().eq('conversation_id', id);
    } catch (e) {
      handleAuthError(e);
      logger.error('Delete conversation error', e instanceof Error ? e : new Error(String(e)));
    }
  }
};
