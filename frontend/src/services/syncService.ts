import { db, getCurrentUserId } from '@/database/db';
import { supabase } from '@/lib/supabase';
import type { AnswerBlock, Conversation, Message, Note } from '@/database/schema';
import { logger } from '@/utils/logger';
import { useAuthStore } from '@/store/auth';
import { normalizeAttachmentMetadata } from '@/utils/attachments';
import { persistentAnswerBlocks } from '@/utils/answerBlocks';
import type { MessageFeedback, MessageFeedbackDetails, MessageFeedbackReason } from '@/database/schema';

type MessageSearchResult = NonNullable<Message['searchResults']>[number];
type MessageSource = NonNullable<Message['sources']>[number];

function normalizeJsonArray<T>(value: unknown, fallback?: T[]): T[] | undefined {
  if (Array.isArray(value)) return value as T[];
  return fallback && fallback.length > 0 ? fallback : undefined;
}

function normalizeReasoning(value: unknown, fallback?: Message['reasoning']): Message['reasoning'] | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return fallback;
  }

  const reasoning = value as Record<string, unknown>;
  if (typeof reasoning.content !== 'string') {
    return fallback;
  }

  return {
    content: reasoning.content,
    ...(typeof reasoning.duration === 'number' ? { duration: reasoning.duration } : {}),
  };
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function handleAuthError(error: unknown): void {
  if ((error as { status?: number } | null)?.status === 401) {
    void useAuthStore.getState().invalidateSession();
  }
}

function normalizeMessageFeedback(value: unknown): MessageFeedback | null {
  return value === 'liked' || value === 'disliked' ? value : null;
}

function normalizeMessageFeedbackReason(value: unknown): MessageFeedbackReason | null {
  return (
    value === 'incorrect_or_incomplete' ||
    value === 'not_what_i_wanted' ||
    value === 'slow_or_broken' ||
    value === 'style_or_tone' ||
    value === 'safety_or_legal' ||
    value === 'other'
  ) ? value : null;
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

      // Pull notes after messages so local references are available when they exist.
      const { data: cloudNotes, error: noteError } = await supabase
        .from('notes')
        .select('*')
        .eq('user_id', userId);

      if (noteError) {
        handleAuthError(noteError);
        throw noteError;
      }

      let dataChanged = false;

      // Group messages by conversation ID to calculate message count
      const msgCountByConv: Record<string, number> = {};
      if (cloudMsgs && cloudMsgs.length > 0) {
        cloudMsgs.forEach(m => {
          msgCountByConv[m.conversation_id] = (msgCountByConv[m.conversation_id] || 0) + 1;
        });
      }

      if (cloudNotes && cloudNotes.length > 0) {
        const localNotes = await db.notes.toArray();
        const localNoteMap = new Map(localNotes.map((note) => [note.id, note]));

        const notesToUpsert = [];
        for (const note of cloudNotes) {
          const cloudUpdatedAt = new Date(note.updated_at);
          const localNote = localNoteMap.get(note.id);
          const cloudAnswerBlocks = normalizeJsonArray<AnswerBlock>(
            note.answer_blocks_snapshot,
            localNote?.answerBlocksSnapshot,
          );
          const cloudCitations = normalizeJsonArray<string>(
            note.citations_snapshot,
            localNote?.citationsSnapshot,
          );
          const cloudSources = normalizeJsonArray<MessageSource>(
            note.sources_snapshot,
            localNote?.sourcesSnapshot,
          );

          if (
            !localNote ||
            localNote.updatedAt.getTime() < cloudUpdatedAt.getTime() ||
            !jsonEqual(localNote.answerBlocksSnapshot, cloudAnswerBlocks) ||
            !jsonEqual(localNote.citationsSnapshot, cloudCitations) ||
            !jsonEqual(localNote.sourcesSnapshot, cloudSources)
          ) {
            notesToUpsert.push({
              id: note.id,
              userId: note.user_id,
              conversationId: note.conversation_id,
              messageId: note.message_id,
              conversationTitle: note.conversation_title ?? null,
              contentSnapshot: note.content_snapshot,
              answerBlocksSnapshot: cloudAnswerBlocks,
              citationsSnapshot: cloudCitations,
              sourcesSnapshot: cloudSources,
              createdAt: new Date(note.created_at),
              updatedAt: cloudUpdatedAt,
            } as Note);
          }
        }

        if (notesToUpsert.length > 0) {
          await db.notes.bulkPut(notesToUpsert);
          dataChanged = true;
        }
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
          const cloudFeedbackReason = normalizeMessageFeedbackReason(m.feedback_reason);
          const cloudFeedbackComment = typeof m.feedback_comment === 'string'
            ? m.feedback_comment
            : null;
          const cloudFeedbackUpdatedAt = m.feedback_updated_at
            ? new Date(m.feedback_updated_at)
            : null;
          const localMsg = localMsgMap.get(m.id);
          const cloudCitations = normalizeJsonArray<string>(m.citations, localMsg?.citations);
          const cloudSearchResults = normalizeJsonArray<MessageSearchResult>(
            m.search_results,
            localMsg?.searchResults,
          );
          const cloudSources = normalizeJsonArray<MessageSource>(
            m.sources,
            localMsg?.sources,
          );
          const cloudAnswerBlocks = normalizeJsonArray<AnswerBlock>(
            m.answer_blocks,
            localMsg?.answerBlocks,
          );
          const cloudSuggestions = normalizeJsonArray<string>(m.suggestions, localMsg?.suggestions);
          const cloudReasoning = normalizeReasoning(m.reasoning, localMsg?.reasoning);

          if (
            !localMsg ||
            (localMsg.feedback ?? null) !== cloudFeedback ||
            (localMsg.feedbackReason ?? null) !== cloudFeedbackReason ||
            (localMsg.feedbackComment ?? null) !== cloudFeedbackComment ||
            (localMsg.feedbackUpdatedAt?.getTime() ?? null) !==
              (cloudFeedbackUpdatedAt?.getTime() ?? null) ||
            !jsonEqual(localMsg.citations, cloudCitations) ||
            !jsonEqual(localMsg.searchResults, cloudSearchResults) ||
            !jsonEqual(localMsg.sources, cloudSources) ||
            !jsonEqual(localMsg.answerBlocks, cloudAnswerBlocks) ||
            !jsonEqual(localMsg.suggestions, cloudSuggestions) ||
            !jsonEqual(localMsg.reasoning, cloudReasoning)
          ) {
            msgsToUpsert.push({
              id: m.id,
              userId: m.user_id,
              conversationId: m.conversation_id,
              role: m.role,
              content: m.content,
              attachments: normalizeAttachmentMetadata(m.attachments),
              feedback: cloudFeedback,
              feedbackReason: cloudFeedbackReason,
              feedbackComment: cloudFeedbackComment,
              feedbackUpdatedAt: cloudFeedbackUpdatedAt,
              citations: cloudCitations,
              searchResults: cloudSearchResults,
              sources: cloudSources,
              answerBlocks: cloudAnswerBlocks,
              suggestions: cloudSuggestions,
              reasoning: cloudReasoning,
              createdAt: new Date(m.created_at)
            } as Message);
          }
        }

        if (msgsToUpsert.length > 0) {
          await db.messages.bulkPut(msgsToUpsert);
          dataChanged = true;
        }
      }

      // Keep cloud reconciliation non-disruptive. A full page reload tears down
      // active chat streams and WebSocket connections, which makes normal
      // background sync look like an unexpected refresh to the user.
      if (dataChanged) {
        logger.info('Pulled updated cloud data into local database');
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
        citations: msg.citations ?? null,
        search_results: msg.searchResults ?? null,
        sources: msg.sources ?? null,
        answer_blocks: persistentAnswerBlocks(msg.answerBlocks) ?? null,
        suggestions: msg.suggestions ?? null,
        reasoning: msg.reasoning ?? null,
        feedback: msg.feedback ?? null,
        feedback_reason: msg.feedbackReason ?? null,
        feedback_comment: msg.feedbackComment ?? null,
        feedback_updated_at: msg.feedbackUpdatedAt?.toISOString() ?? null,
        created_at: msg.createdAt.toISOString(),
      });
    } catch (e) {
      handleAuthError(e);
      logger.error('Push message error', e instanceof Error ? e : new Error(String(e)));
    }
  },

  /**
   * Pushes a note to Supabase.
   *
   * The payload intentionally includes source identifiers and safe display
   * snapshots, but does not emit the note content to logs.
   */
  async pushNote(note: Note) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      const { error } = await supabase.from('notes').upsert({
        id: note.id,
        user_id: note.userId,
        conversation_id: note.conversationId,
        message_id: note.messageId,
        conversation_title: note.conversationTitle ?? null,
        content_snapshot: note.contentSnapshot,
        answer_blocks_snapshot: persistentAnswerBlocks(note.answerBlocksSnapshot) ?? null,
        citations_snapshot: note.citationsSnapshot ?? null,
        sources_snapshot: note.sourcesSnapshot ?? null,
        created_at: note.createdAt.toISOString(),
        updated_at: note.updatedAt.toISOString(),
      });

      if (error) {
        handleAuthError(error);
        throw error;
      }

      logger.info('note_synced_to_cloud', {
        component: 'syncService',
        noteId: note.id,
        conversationId: note.conversationId ?? null,
        messageId: note.messageId ?? null,
      });
    } catch (e) {
      handleAuthError(e);
      logger.error('Push note error', e instanceof Error ? e : new Error(String(e)), {
        component: 'syncService',
        noteId: note.id,
      });
    }
  },

  /**
   * Updates only the assistant-feedback fields for an existing cloud message.
   */
  async updateMessageFeedback(
    messageId: string,
    feedback: MessageFeedback | null,
    feedbackUpdatedAt: Date | null,
    details: MessageFeedbackDetails = {}
  ) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      const { data, error } = await supabase
        .from('messages')
        .update({
          feedback,
          feedback_reason: feedback === 'disliked' ? details.reason ?? null : null,
          feedback_comment: feedback === 'disliked' ? details.comment ?? null : null,
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
   * Deletes one message from Supabase for the current user.
   *
   * Local message deletion is used by edit/regenerate flows to remove
   * superseded assistant replies. The cloud delete keeps reload-time sync from
   * reintroducing those stale replies into IndexedDB.
   */
  async deleteMessage(id: string) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      await supabase
        .from('messages')
        .delete()
        .eq('id', id)
        .eq('user_id', userId);
    } catch (e) {
      handleAuthError(e);
      logger.error('Delete message error', e instanceof Error ? e : new Error(String(e)));
    }
  },

  /**
   * Deletes one note from Supabase for the current user.
   */
  async deleteNote(id: string) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      const { error } = await supabase
        .from('notes')
        .delete()
        .eq('id', id)
        .eq('user_id', userId);

      if (error) {
        handleAuthError(error);
        throw error;
      }
    } catch (e) {
      handleAuthError(e);
      logger.error('Delete note error', e instanceof Error ? e : new Error(String(e)), {
        component: 'syncService',
        noteId: id,
      });
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
