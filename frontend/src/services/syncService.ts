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
const MESSAGE_DELETION_TOMBSTONE_RETENTION_MS = 30 * 24 * 60 * 60 * 1000;
const CLOUD_SYNC_PAGE_SIZE = 1000;

type CloudQueryResult<T> = { data: T[] | null; error: unknown };
type CloudQuery<T> = {
  eq: (column: string, value: unknown) => CloudQuery<T>;
  order: (column: string, options?: { ascending?: boolean }) => CloudQuery<T>;
  range: (from: number, to: number) => Promise<CloudQueryResult<T>>;
};

type CloudConversationRow = {
  id: string;
  user_id: string;
  title: string;
  branch_origin?: Conversation['branchOrigin'] | null;
  created_at: string;
  updated_at: string;
};

type CloudMessageRow = {
  id: string;
  user_id: string;
  conversation_id: string;
  role: Message['role'];
  content: string;
  attachments?: unknown;
  attachment_source_id?: string | null;
  citations?: unknown;
  search_results?: unknown;
  sources?: unknown;
  answer_blocks?: unknown;
  suggestions?: unknown;
  reasoning?: unknown;
  feedback?: unknown;
  feedback_reason?: unknown;
  feedback_comment?: unknown;
  feedback_updated_at?: string | null;
  created_at: string;
  updated_at?: string | null;
};

type CloudNoteRow = {
  id: string;
  user_id: string;
  conversation_id: string | null;
  message_id: string | null;
  conversation_title?: string | null;
  content_snapshot: string;
  answer_blocks_snapshot?: unknown;
  citations_snapshot?: unknown;
  sources_snapshot?: unknown;
  tags?: unknown;
  is_pinned?: unknown;
  created_at: string;
  updated_at: string;
};

function normalizeJsonArray<T>(value: unknown, fallback?: T[]): T[] | undefined {
  if (Array.isArray(value)) return value as T[];
  if (value === null) return undefined;
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

function localMessageUpdatedAt(message: Message): Date {
  return message.updatedAt ?? message.createdAt;
}

function handleAuthError(error: unknown): void {
  if ((error as { status?: number } | null)?.status === 401) {
    void useAuthStore.getState().invalidateSession();
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return String(error);
}

async function pruneExpiredMessageDeletionTombstones(userId: string): Promise<void> {
  const expiresBefore = new Date(Date.now() - MESSAGE_DELETION_TOMBSTONE_RETENTION_MS);
  await db.messageDeletions
    .where('[userId+deletedAt]')
    .below([userId, expiresBefore])
    .delete();
}

async function fetchCloudRows<T>(
  table: string,
  userId: string,
  applyFilters?: (query: CloudQuery<T>) => CloudQuery<T>,
): Promise<T[]> {
  const rows: T[] = [];
  let pageStart = 0;

  while (true) {
    let query = supabase
      .from(table)
      .select('*')
      .eq('user_id', userId) as unknown as CloudQuery<T>;

    if (applyFilters) {
      query = applyFilters(query);
    }

    const { data, error } = await query
      .order('created_at', { ascending: true })
      .order('id', { ascending: true })
      .range(pageStart, pageStart + CLOUD_SYNC_PAGE_SIZE - 1);

    if (error) {
      handleAuthError(error);
      throw error;
    }

    const page = data ?? [];
    rows.push(...page);

    if (page.length < CLOUD_SYNC_PAGE_SIZE) {
      return rows;
    }

    pageStart += CLOUD_SYNC_PAGE_SIZE;
  }
}

async function mergeCloudNotes(cloudNotes: CloudNoteRow[]): Promise<boolean> {
  if (cloudNotes.length === 0) return false;

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
    const cloudTags = normalizeJsonArray<string>(note.tags, localNote?.tags ?? []) ?? [];
    const cloudIsPinned = Boolean(note.is_pinned);

    if (!localNote || localNote.updatedAt.getTime() < cloudUpdatedAt.getTime()) {
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
        tags: cloudTags,
        isPinned: cloudIsPinned,
        createdAt: new Date(note.created_at),
        updatedAt: cloudUpdatedAt,
      } as Note);
    }
  }

  if (notesToUpsert.length === 0) return false;

  await db.notes.bulkPut(notesToUpsert);
  return true;
}

async function mergeCloudConversations(
  cloudConvs: CloudConversationRow[],
  msgCountByConv: Record<string, number>,
): Promise<boolean> {
  if (cloudConvs.length === 0) return false;

  const localConvs = await db.conversations.toArray();
  const localConvMap = new Map(localConvs.map(c => [c.id, c]));
  const pendingConversationIds = new Set(
    (await db.conversationSyncQueue.toArray()).map((row) => row.id),
  );

  const convsToUpsert = [];
  for (const c of cloudConvs) {
    const cloudDate = new Date(c.updated_at);
    const localConv = localConvMap.get(c.id);
    if (localConv && pendingConversationIds.has(c.id)) continue;
    if (!localConv || localConv.updatedAt.getTime() < cloudDate.getTime()) {
      convsToUpsert.push({
        id: c.id,
        userId: c.user_id,
        title: c.title,
        branchOrigin: c.branch_origin ?? undefined,
        createdAt: new Date(c.created_at),
        updatedAt: cloudDate,
        messageCount: msgCountByConv[c.id] || 0,
        lastMessagePreview: ''
      } as Conversation);
    }
  }

  if (convsToUpsert.length === 0) return false;

  await db.conversations.bulkPut(convsToUpsert);
  return true;
}

async function updateLocalConversationMessageCounts(
  msgCountByConv: Record<string, number>,
): Promise<boolean> {
  let changed = false;

  for (const [conversationId, messageCount] of Object.entries(msgCountByConv)) {
    const localConv = await db.conversations.get(conversationId);
    if (localConv && localConv.messageCount !== messageCount) {
      await db.conversations.update(conversationId, { messageCount });
      changed = true;
    }
  }

  return changed;
}

async function mergeCloudMessages(userId: string, cloudMsgs: CloudMessageRow[]): Promise<boolean> {
  if (cloudMsgs.length === 0) return false;

  const localMsgs = await db.messages.toArray();
  const localMsgMap = new Map(localMsgs.map(m => [m.id, m]));
  const pendingMessageIds = new Set(
    (await db.messageSyncQueue.where('userId').equals(userId).toArray())
      .map((row) => row.id),
  );
  const deletedMessageIds = new Set(
    (await db.messageDeletions.where('userId').equals(userId).toArray())
      .map((deletion) => deletion.id),
  );

  const msgsToUpsert = [];
  for (const m of cloudMsgs) {
    if (pendingMessageIds.has(m.id) && localMsgMap.has(m.id)) continue;
    if (deletedMessageIds.has(m.id)) {
      logger.info('sync_message_pull_tombstone_skipped', {
        component: 'syncService',
        messageId: m.id,
        conversationId: m.conversation_id,
      });
      continue;
    }
    const cloudUpdatedAt = m.updated_at
      ? new Date(m.updated_at)
      : new Date(m.created_at);
    const cloudFeedback = normalizeMessageFeedback(m.feedback);
    const cloudFeedbackReason = normalizeMessageFeedbackReason(m.feedback_reason);
    const cloudFeedbackComment = typeof m.feedback_comment === 'string'
      ? m.feedback_comment
      : null;
    const cloudFeedbackUpdatedAt = m.feedback_updated_at
      ? new Date(m.feedback_updated_at)
      : null;
    const localMsg = localMsgMap.get(m.id);
    const cloudIsNewer = !localMsg || localMessageUpdatedAt(localMsg).getTime() < cloudUpdatedAt.getTime();
    const cloudCitations = cloudIsNewer
      ? normalizeJsonArray<string>(m.citations, localMsg?.citations)
      : localMsg?.citations;
    const cloudSearchResults = normalizeJsonArray<MessageSearchResult>(
      cloudIsNewer ? m.search_results : undefined,
      localMsg?.searchResults,
    );
    const cloudSources = normalizeJsonArray<MessageSource>(
      cloudIsNewer ? m.sources : undefined,
      localMsg?.sources,
    );
    const cloudAnswerBlocks = normalizeJsonArray<AnswerBlock>(
      cloudIsNewer ? m.answer_blocks : undefined,
      localMsg?.answerBlocks,
    );
    const cloudSuggestions = cloudIsNewer
      ? normalizeJsonArray<string>(m.suggestions, localMsg?.suggestions)
      : localMsg?.suggestions;
    const cloudReasoning = cloudIsNewer
      ? normalizeReasoning(m.reasoning, localMsg?.reasoning)
      : localMsg?.reasoning;
    const nextContent = cloudIsNewer ? m.content : localMsg?.content;
    const nextAttachments = cloudIsNewer ? normalizeAttachmentMetadata(m.attachments) : localMsg?.attachments;

    if (
      !localMsg ||
      cloudIsNewer ||
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
        content: nextContent,
        attachments: nextAttachments,
        attachmentSourceId: cloudIsNewer ? m.attachment_source_id ?? undefined : localMsg?.attachmentSourceId,
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
        createdAt: new Date(m.created_at),
        updatedAt: cloudIsNewer ? cloudUpdatedAt : localMsg?.updatedAt,
      } as Message);
    }
  }

  if (msgsToUpsert.length === 0) return false;

  await db.messages.bulkPut(msgsToUpsert);
  return true;
}

function messageFromCloudRow(m: CloudMessageRow): Message {
  const cloudUpdatedAt = m.updated_at
    ? new Date(m.updated_at)
    : new Date(m.created_at);

  return {
    id: m.id,
    userId: m.user_id,
    conversationId: m.conversation_id,
    role: m.role,
    content: m.content,
    attachments: normalizeAttachmentMetadata(m.attachments),
    attachmentSourceId: m.attachment_source_id ?? undefined,
    feedback: normalizeMessageFeedback(m.feedback),
    feedbackReason: normalizeMessageFeedbackReason(m.feedback_reason),
    feedbackComment: typeof m.feedback_comment === 'string' ? m.feedback_comment : null,
    feedbackUpdatedAt: m.feedback_updated_at ? new Date(m.feedback_updated_at) : null,
    citations: normalizeJsonArray<string>(m.citations),
    searchResults: normalizeJsonArray<MessageSearchResult>(m.search_results),
    sources: normalizeJsonArray<MessageSource>(m.sources),
    answerBlocks: normalizeJsonArray<AnswerBlock>(m.answer_blocks),
    suggestions: normalizeJsonArray<string>(m.suggestions),
    reasoning: normalizeReasoning(m.reasoning),
    createdAt: new Date(m.created_at),
    updatedAt: cloudUpdatedAt,
  };
}

async function replaceLocalConversationMessagesFromCloud(
  userId: string,
  conversationId: string,
  cloudMsgs: CloudMessageRow[],
): Promise<boolean> {
  return db.transaction(
    'rw',
    [db.messages, db.conversations, db.messageSyncQueue, db.messageDeletions],
    async () => {
      const [localMessages, pendingRows, deletionRows] = await Promise.all([
        db.messages.where('conversationId').equals(conversationId)
          .filter((message) => message.userId === userId).toArray(),
        db.messageSyncQueue.where('conversationId').equals(conversationId)
          .filter((row) => row.userId === userId).toArray(),
        db.messageDeletions.where('conversationId').equals(conversationId)
          .filter((row) => row.userId === userId).toArray(),
      ]);

      // An empty cloud snapshot cannot prove that local-only messages were saved.
      if (cloudMsgs.length === 0 && localMessages.length > 0) {
        logger.warn('sync_empty_cloud_snapshot_local_preserved', {
          component: 'syncService',
          conversationId,
          localMessageCount: localMessages.length,
          pendingSyncCount: pendingRows.length,
        });
        return false;
      }

      const deletedIds = new Set(deletionRows.map((row) => row.id));
      const pendingIds = new Set(pendingRows.map((row) => row.id));
      const localById = new Map(localMessages.map((message) => [message.id, message]));
      const merged = new Map<string, Message>();
      for (const row of cloudMsgs) {
        if (deletedIds.has(row.id)) continue;
        const cloudMessage = messageFromCloudRow(row);
        const localMessage = localById.get(row.id);
        merged.set(row.id, localMessage && (
          pendingIds.has(row.id) ||
          localMessageUpdatedAt(localMessage).getTime() > localMessageUpdatedAt(cloudMessage).getTime()
        ) ? localMessage : cloudMessage);
      }
      for (const message of localMessages) {
        if (pendingIds.has(message.id) && !deletedIds.has(message.id)) {
          merged.set(message.id, message);
        }
      }

      const obsoleteIds = localMessages
        .filter((message) => !merged.has(message.id))
        .map((message) => message.id);
      if (obsoleteIds.length > 0) {
        await db.messages.bulkDelete(obsoleteIds);
      }
      const messages = [...merged.values()].sort((a, b) =>
        a.createdAt.getTime() - b.createdAt.getTime() || a.id.localeCompare(b.id));
      if (messages.length > 0) await db.messages.bulkPut(messages);
      const latestMessage = messages.at(-1);
      await db.conversations.update(conversationId, {
        messageCount: messages.length,
        lastMessagePreview: latestMessage?.content.slice(0, 100) ?? '',
        updatedAt: latestMessage
          ? localMessageUpdatedAt(latestMessage)
          : new Date(),
      });
      logger.info('sync_conversation_snapshot_reconciled', {
        component: 'syncService',
        conversationId,
        cloudMessageCount: cloudMsgs.length,
        localMessageCount: localMessages.length,
        pendingSyncCount: pendingRows.length,
        deletionMarkerCount: deletionRows.length,
        resultingMessageCount: messages.length,
      });
      return obsoleteIds.length > 0 || messages.length !== localMessages.length ||
        messages.some((message) => {
          const local = localById.get(message.id);
          return !local || localMessageUpdatedAt(local).getTime() !== localMessageUpdatedAt(message).getTime();
        });
    },
  );
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
      const cloudConvs = await fetchCloudRows<CloudConversationRow>('conversations', userId);
      const cloudMsgs = await fetchCloudRows<CloudMessageRow>('messages', userId);
      let dataChanged = false;

      // Group messages by conversation ID to calculate message count
      const msgCountByConv: Record<string, number> = {};
      cloudMsgs.forEach(m => {
        msgCountByConv[m.conversation_id] = (msgCountByConv[m.conversation_id] || 0) + 1;
      });

      if (await mergeCloudConversations(cloudConvs, msgCountByConv)) {
        dataChanged = true;
      }
      if (await mergeCloudMessages(userId, cloudMsgs)) {
        dataChanged = true;
      }
      if (await updateLocalConversationMessageCounts(msgCountByConv)) {
        dataChanged = true;
      }

      try {
        // Notes are secondary metadata. A notes pull failure should not prevent
        // conversations and messages from hydrating on a fresh device.
        const cloudNotes = await fetchCloudRows<CloudNoteRow>('notes', userId);
        if (await mergeCloudNotes(cloudNotes)) {
          dataChanged = true;
        }
      } catch (noteError) {
        handleAuthError(noteError);
        logger.error(
          'sync_notes_pull_failed',
          noteError instanceof Error ? noteError : new Error(String(noteError)),
          { component: 'syncService' },
        );
      }

      // Keep cloud reconciliation non-disruptive. A full page reload tears down
      // active chat streams and WebSocket connections, which makes normal
      // background sync look like an unexpected refresh to the user.
      if (dataChanged) {
        logger.info('Pulled updated cloud data into local database');
      }
      await pruneExpiredMessageDeletionTombstones(userId);
    } catch (e) {
      handleAuthError(e);
      logger.error('Failed to sync from cloud', e instanceof Error ? e : new Error(String(e)));
    }
  },

  /**
   * Pulls messages for one conversation from Supabase.
   *
   * Args:
   *   conversationId: Conversation to hydrate.
   *   overrideUserId: Optional authenticated user ID already known by caller.
   *
   * Returns:
   *   True when local data changed. A false return can also mean the cloud
   *   request failed and local cache should remain available as a fallback.
   *
   * Side Effects:
   *   Reconciles the cloud snapshot with local pending writes and deletion
   *   markers. Logs only safe IDs and counters.
   */
  async pullConversationMessages(
    conversationId: string,
    overrideUserId?: string,
    options: { authoritative?: boolean } = {},
  ): Promise<boolean> {
    const userId = overrideUserId || getCurrentUserId();
    if (!userId || userId === 'default_user') return false;
    const authoritative = options.authoritative ?? true;

    try {
      const cloudMsgs = await fetchCloudRows<CloudMessageRow>(
        'messages',
        userId,
        (query) => query.eq('conversation_id', conversationId),
      );
      const msgCountByConv: Record<string, number> = {
        [conversationId]: cloudMsgs.length,
      };
      let dataChanged = false;

      if (authoritative) {
        dataChanged = await replaceLocalConversationMessagesFromCloud(
          userId,
          conversationId,
          cloudMsgs,
        );
      } else if (await mergeCloudMessages(userId, cloudMsgs)) {
        dataChanged = true;
      }
      if (!authoritative && await updateLocalConversationMessageCounts(msgCountByConv)) {
        dataChanged = true;
      }

      logger.info('sync_conversation_messages_pulled', {
        component: 'syncService',
        conversationId,
        cloudMessageCount: cloudMsgs.length,
        dataChanged,
        authoritative,
      });

      return dataChanged;
    } catch (e) {
      handleAuthError(e);
      logger.error('sync_conversation_messages_pull_failed', e instanceof Error ? e : new Error(String(e)), {
        component: 'syncService',
        conversationId,
      });
      return false;
    }
  },

  /**
   * Pushes a conversation to Supabase
   */
  async pushConversation(conv: Conversation): Promise<boolean> {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return false;

    try {
      const { error } = await supabase.from('conversations').upsert({
        id: conv.id,
        user_id: conv.userId,
        title: conv.title,
        ...(conv.branchOrigin ? { branch_origin: conv.branchOrigin } : {}),
        created_at: conv.createdAt.toISOString(),
        updated_at: conv.updatedAt.toISOString(),
      });
      if (error) throw error;
      return true;
    } catch (e) {
      handleAuthError(e);
      logger.error('Push conversation error', e instanceof Error ? e : new Error(errorMessage(e)), {
        component: 'syncService',
        conversationId: conv.id,
      });
      return false;
    }
  },

  /**
   * Pushes a message to Supabase
   */
  async pushMessage(msg: Message) {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return;

    try {
      const pendingDeletion = await db.messageDeletions.get(msg.id);
      if (pendingDeletion?.userId === userId) {
        logger.warn('sync_message_push_skipped_for_tombstone', {
          component: 'syncService',
          messageId: msg.id,
          conversationId: msg.conversationId,
        });
        return;
      }

      const payload = {
        id: msg.id,
        user_id: msg.userId,
        conversation_id: msg.conversationId,
        role: msg.role,
        content: msg.content,
        attachments: normalizeAttachmentMetadata(msg.attachments),
        ...(msg.attachmentSourceId ? { attachment_source_id: msg.attachmentSourceId } : {}),
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
        updated_at: (msg.updatedAt ?? msg.createdAt).toISOString(),
      };
      let { error } = await supabase.from('messages').upsert(payload);

      if (error?.code === '23503') {
        const conversation = await db.conversations.get(msg.conversationId);
        if (conversation?.userId === userId && await syncService.pushConversation(conversation)) {
          ({ error } = await supabase.from('messages').upsert(payload));
        }
      }

      if (error) {
        handleAuthError(error);
        throw error;
      }
    } catch (e) {
      handleAuthError(e);
      logger.error('Push message error', e instanceof Error ? e : new Error(String(e)), {
        component: 'syncService',
        messageId: msg.id,
        conversationId: msg.conversationId,
      });
      throw e;
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
        tags: note.tags ?? [],
        is_pinned: Boolean(note.isPinned),
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
      throw e;
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
  async deleteMessage(id: string): Promise<boolean> {
    const userId = getCurrentUserId();
    if (!userId || userId === 'default_user') return false;

    try {
      const { error } = await supabase
        .from('messages')
        .delete()
        .eq('id', id)
        .eq('user_id', userId);

      if (error) {
        handleAuthError(error);
        throw error;
      }

      await db.messageDeletions
        .where('id')
        .equals(id)
        .modify((deletion) => {
          deletion.retryCount = (deletion.retryCount || 0) + 1;
          deletion.lastError = null;
        });
      logger.info('sync_message_deleted_from_cloud', {
        component: 'syncService',
        messageId: id,
      });
      return true;
    } catch (e) {
      handleAuthError(e);
      await db.messageDeletions
        .where('id')
        .equals(id)
        .modify((deletion) => {
          deletion.retryCount = (deletion.retryCount || 0) + 1;
          deletion.lastError = errorMessage(e);
        });
      logger.error('Delete message error', e instanceof Error ? e : new Error(errorMessage(e)), {
        component: 'syncService',
        messageId: id,
      });
      return false;
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
