/**
 * Sync for collaborative conversations inside the normal chat.
 *
 * A participant keeps a local copy of the owner's conversation in their own
 * history (`conversation.collaboration.role === 'editor'`). Those copies never
 * touch the owner-only `conversations` / `messages` rows directly: reads and
 * writes go through the Supabase security definer functions, which check
 * membership with the caller's JWT, keep the owner as `user_id` and record
 * the caller as author. Owners keep their ordinary sync; their conversation
 * is only marked `role: 'owner'` so the chat refreshes it while open.
 *
 * Every function fails soft: a missing migration or network error leaves the
 * ordinary chat untouched.
 */
import { db } from '@/database/db';
import { supabase } from '@/lib/supabase';
import type { Conversation, ConversationCollaboration, Message } from '@/database/schema';
import { normalizeAttachmentMetadata } from '@/utils/attachments';
import { persistentAnswerBlocks } from '@/utils/answerBlocks';
import { TOPIC_FINDER_KIND, normalizeConversationKind } from '@/utils/conversationKind';
import { logger } from '@/utils/logger';

/** Open collaborative conversations refresh at this interval (no realtime yet). */
export const COLLABORATIVE_REFRESH_INTERVAL_MS = 5000;

interface CollaborativeSummary {
  id: string;
  title: string;
  kind?: string | null;
  role: ConversationCollaboration['role'];
  ownerUserId: string;
  createdAt: string;
  updatedAt: string;
}

interface CollaborativeMessagePayload {
  id: string;
  role: Message['role'];
  content: string;
  citations?: unknown;
  searchResults?: unknown;
  sources?: unknown;
  answerBlocks?: unknown;
  suggestions?: unknown;
  attachments?: unknown;
  requestModes?: unknown;
  stoppedByUser?: boolean | null;
  authorUserId?: string | null;
  authorName?: string | null;
  authorAvatarUrl?: string | null;
  createdAt: string;
  updatedAt?: string | null;
}

/** Same shape as the owner-table rows, so the existing reconciliation can merge it. */
export interface CollaborativeCloudRow {
  id: string;
  user_id: string;
  conversation_id: string;
  role: Message['role'];
  content: string;
  attachments?: unknown;
  citations?: unknown;
  search_results?: unknown;
  sources?: unknown;
  answer_blocks?: unknown;
  suggestions?: unknown;
  request_modes?: unknown;
  stopped_by_user?: boolean | null;
  author_user_id?: string | null;
  author_name?: string | null;
  author_avatar_url?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export class CollaborationAccessError extends Error {
  constructor() {
    super('collaboration_access_denied');
    this.name = 'CollaborationAccessError';
  }
}

export function isMemberConversation(conversation?: Pick<Conversation, 'collaboration'> | null): boolean {
  return conversation?.collaboration?.role === 'editor';
}

export function isCollaborativeConversation(conversation?: Pick<Conversation, 'collaboration'> | null): boolean {
  return Boolean(conversation?.collaboration);
}

function isAccessError(error: { code?: string } | null | undefined): boolean {
  return error?.code === '42501';
}

/**
 * Join through an edit share link and store the local copy.
 *
 * Returns the conversation id, or null when the link cannot be joined.
 * Owners opening their own link get their own id back unchanged.
 */
export async function joinCollaborativeShare(token: string, userId: string, title: string): Promise<string | null> {
  const { data, error } = await supabase.rpc('join_conversation_share', { p_share_token: token });
  if (error || typeof data !== 'string') {
    logger.warn('collab_join_failed', { component: 'collaborationSync', code: error?.code });
    return null;
  }
  const existing = await db.conversations.get(data);
  if (existing?.userId === userId && !isMemberConversation(existing)) return data;

  await syncCollaborativeConversationList(userId, { fallbackTitle: { id: data, title } });
  if (!isMemberConversation(await db.conversations.get(data))) {
    // Without the local copy (e.g. the in-app migration is missing) the caller
    // shows the read-only share instead of opening an empty conversation.
    logger.warn('collab_join_local_copy_missing', { component: 'collaborationSync', conversationId: data });
    return null;
  }
  logger.info('collab_joined', { component: 'collaborationSync', conversationId: data });
  return data;
}

/**
 * Reconcile local copies with the conversations the caller currently shares.
 *
 * Adds new participant copies, refreshes their titles, drops copies whose
 * access ended (removed, or the link went back to view-only) and marks the
 * owner's shared conversations. Returns true when local data changed.
 */
export async function syncCollaborativeConversationList(
  userId: string,
  options: { fallbackTitle?: { id: string; title: string } } = {},
): Promise<boolean> {
  const { data, error } = await supabase.rpc('list_my_collaborative_conversations');
  if (error || !Array.isArray(data)) {
    // PGRST202: the migration is not applied yet. Keep local state as is.
    if (error) logger.warn('collab_list_failed', { component: 'collaborationSync', code: error.code });
    return false;
  }

  const shared = new Map((data as CollaborativeSummary[]).map((item) => [item.id, item]));
  const localConversations = await db.conversations.where('userId').equals(userId).toArray();
  const localById = new Map(localConversations.map((conversation) => [conversation.id, conversation]));
  let changed = false;

  for (const item of shared.values()) {
    const local = localById.get(item.id);
    const collaboration: ConversationCollaboration = { role: item.role, ownerUserId: item.ownerUserId };

    if (item.role === 'owner') {
      if (local && local.collaboration?.role !== 'owner') {
        await db.conversations.update(item.id, { collaboration });
        changed = true;
      }
      continue;
    }

    const foreign = await db.conversations.get(item.id);
    if (foreign && foreign.userId !== userId) {
      // Another account in this browser (often the owner) holds this id. The
      // cloud is the source of truth, so take the row over unless that account
      // still has unsynced changes here; its next sync takes it back.
      if (await hasPendingSync(item.id, foreign.userId)) {
        logger.warn('collab_local_copy_conflict', { component: 'collaborationSync', conversationId: item.id });
        continue;
      }
      logger.info('collab_local_copy_taken_over', { component: 'collaborationSync', conversationId: item.id });
    }
    const title = item.title || (options.fallbackTitle?.id === item.id ? options.fallbackTitle.title : '');
    const updatedAt = new Date(item.updatedAt);
    if (local && local.title === title && local.updatedAt.getTime() >= updatedAt.getTime() && isMemberConversation(local)) {
      continue;
    }
    await db.conversations.put({
      id: item.id,
      userId,
      title,
      createdAt: local?.createdAt ?? new Date(item.createdAt),
      updatedAt,
      messageCount: local?.messageCount ?? 0,
      lastMessagePreview: local?.lastMessagePreview ?? '',
      ...(normalizeConversationKind(item.kind) === TOPIC_FINDER_KIND ? { kind: TOPIC_FINDER_KIND } : {}),
      collaboration,
    });
    changed = true;
  }

  for (const local of localConversations) {
    if (!local.collaboration || shared.has(local.id)) continue;
    if (isMemberConversation(local)) {
      await removeLocalCopy(local.id, userId);
      logger.info('collab_access_ended_local_copy_removed', { component: 'collaborationSync', conversationId: local.id });
    } else {
      await db.conversations.update(local.id, { collaboration: undefined });
    }
    changed = true;
  }

  return changed;
}

async function hasPendingSync(conversationId: string, userId: string): Promise<boolean> {
  if (await db.conversationSyncQueue.get(conversationId)) return true;
  const pendingMessages = await db.messageSyncQueue.where('conversationId').equals(conversationId)
    .filter((row) => row.userId === userId).count();
  return pendingMessages > 0;
}

async function removeLocalCopy(conversationId: string, userId: string): Promise<void> {
  await db.transaction('rw', [db.conversations, db.messages, db.messageSyncQueue, db.conversationSyncQueue], async () => {
    const messageIds = (await db.messages.where('conversationId').equals(conversationId)
      .filter((message) => message.userId === userId).primaryKeys()) as string[];
    await db.messages.bulkDelete(messageIds);
    await db.messageSyncQueue.bulkDelete(messageIds);
    await db.conversationSyncQueue.delete(conversationId);
    await db.conversations.delete(conversationId);
  });
}

/**
 * Stored messages of a shared conversation, mapped onto local rows owned by
 * the participant. Throws CollaborationAccessError when access ended.
 */
export async function fetchCollaborativeMessageRows(
  conversationId: string,
  userId: string,
): Promise<CollaborativeCloudRow[]> {
  const { data, error } = await supabase.rpc('get_collaborative_conversation', { p_conversation_id: conversationId });
  if (error) {
    if (isAccessError(error)) throw new CollaborationAccessError();
    throw error;
  }
  if (!data || typeof data !== 'object') throw new CollaborationAccessError();

  const messages = Array.isArray((data as { messages?: unknown }).messages)
    ? (data as { messages: CollaborativeMessagePayload[] }).messages
    : [];
  return messages.map((message) => ({
    id: message.id,
    user_id: userId,
    conversation_id: conversationId,
    role: message.role,
    content: typeof message.content === 'string' ? message.content : '',
    attachments: message.attachments,
    citations: message.citations,
    search_results: message.searchResults,
    sources: message.sources,
    answer_blocks: message.answerBlocks,
    suggestions: message.suggestions,
    request_modes: message.requestModes,
    stopped_by_user: message.stoppedByUser ?? null,
    author_user_id: message.authorUserId ?? null,
    author_name: message.authorName ?? null,
    author_avatar_url: message.authorAvatarUrl ?? null,
    created_at: message.createdAt,
    updated_at: message.updatedAt ?? message.createdAt,
  }));
}

/** Store a participant's message; repeated pushes of the same id update it. */
export async function upsertCollaborativeMessage(message: Message): Promise<void> {
  const { error } = await supabase.rpc('append_collaborative_message', {
    p_conversation_id: message.conversationId,
    p_message: {
      id: message.id,
      role: message.role,
      content: message.content,
      attachments: normalizeAttachmentMetadata(message.attachments),
      citations: message.citations ?? null,
      searchResults: message.searchResults ?? null,
      sources: message.sources ?? null,
      answerBlocks: persistentAnswerBlocks(message.answerBlocks) ?? null,
      suggestions: message.suggestions ?? null,
      requestModes: message.requestModes ?? null,
      stoppedByUser: message.stoppedByUser === true,
    },
  });
  if (error) {
    if (isAccessError(error)) throw new CollaborationAccessError();
    throw error;
  }
}

/** Remove a message the participant wrote (edit/regenerate flows). */
export async function deleteOwnCollaborativeMessage(conversationId: string, messageId: string): Promise<void> {
  const { error } = await supabase.rpc('delete_own_collaborative_message', {
    p_conversation_id: conversationId,
    p_message_id: messageId,
  });
  if (error) {
    if (isAccessError(error)) throw new CollaborationAccessError();
    throw error;
  }
}

/** Deleting a participant copy from the sidebar means leaving the conversation. */
export async function leaveCollaborativeConversation(conversationId: string, userId: string): Promise<void> {
  const { error } = await supabase
    .from('conversation_members')
    .delete()
    .eq('conversation_id', conversationId)
    .eq('user_id', userId);
  if (error) {
    logger.warn('collab_leave_failed', { component: 'collaborationSync', conversationId, code: error.code });
    return;
  }
  logger.info('collab_left', { component: 'collaborationSync', conversationId });
}

/** Mark or unmark the owner's own conversation as shared with participants. */
export async function markOwnerCollaboration(
  conversationId: string,
  ownerUserId: string,
  shared: boolean,
): Promise<ConversationCollaboration | undefined> {
  const collaboration: ConversationCollaboration | undefined = shared
    ? { role: 'owner', ownerUserId }
    : undefined;
  await db.conversations.update(conversationId, { collaboration });
  return collaboration;
}
