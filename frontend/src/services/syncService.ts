import { db, getCurrentUserId } from '@/database/db';
import { supabase } from '@/lib/supabase';
import type { Conversation, Message } from '@/database/schema';
import { logger } from '@/utils/logger';

export const syncService = {
  /**
   * Pulls all conversations and messages from Supabase for the current user
   * and merges them into the local Dexie DB.
   */
  async pullFromCloud() {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      // Pull conversations
      const { data: cloudConvs, error: convError } = await supabase
        .from('conversations')
        .select('*')
        .eq('user_id', userId);
        
      if (convError) throw convError;

      // Pull messages
      const { data: cloudMsgs, error: msgError } = await supabase
        .from('messages')
        .select('*')
        .eq('user_id', userId);

      if (msgError) throw msgError;

      let dataChanged = false;

      // Group messages by conversation ID to calculate message count
      const msgCountByConv: Record<string, number> = {};
      if (cloudMsgs && cloudMsgs.length > 0) {
        cloudMsgs.forEach(m => {
          msgCountByConv[m.conversation_id] = (msgCountByConv[m.conversation_id] || 0) + 1;
        });
      }

      if (cloudConvs && cloudConvs.length > 0) {
        const convsToUpsert = cloudConvs.map(c => ({
          id: c.id,
          userId: c.user_id,
          title: c.title,
          createdAt: new Date(c.created_at),
          updatedAt: new Date(c.updated_at),
          messageCount: msgCountByConv[c.id] || 0,
          lastMessagePreview: '' // We could derive this from the last message if needed
        } as Conversation));

        await db.conversations.bulkPut(convsToUpsert);
        dataChanged = true;
      }

      if (cloudMsgs && cloudMsgs.length > 0) {
        const msgsToUpsert = cloudMsgs.map(m => ({
          id: m.id,
          userId: m.user_id,
          conversationId: m.conversation_id,
          role: m.role,
          content: m.content,
          createdAt: new Date(m.created_at)
        } as Message));

        await db.messages.bulkPut(msgsToUpsert);
        dataChanged = true;
      }

      // Only reload if we actually pulled new data
      if (dataChanged) {
        window.location.reload();
      }
    } catch (e) {
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
        created_at: msg.createdAt.toISOString(),
      });
    } catch (e) {
      logger.error('Push message error', e instanceof Error ? e : new Error(String(e)));
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
    } catch (e) {
      logger.error('Delete conversation error', e instanceof Error ? e : new Error(String(e)));
    }
  }
};
