/**
 * Topic Finder (選題) workspace helpers.
 *
 * A conversation's kind is fixed at creation. Rows created before Topic Finder
 * (or synced from an older client) have no kind and count as ordinary chat.
 */

import type { Conversation, ConversationKind } from '@/database/schema';

export const TOPIC_FINDER_KIND: ConversationKind = 'research_coach';

/** Return a supported kind, treating anything unknown as ordinary chat. */
export function normalizeConversationKind(value: unknown): ConversationKind {
  return value === TOPIC_FINDER_KIND ? TOPIC_FINDER_KIND : 'chat';
}

/** Kind of a stored conversation; missing or unknown values are `chat`. */
export function conversationKindOf(conversation: Pick<Conversation, 'kind'> | null | undefined): ConversationKind {
  return normalizeConversationKind(conversation?.kind);
}

/**
 * Kind of the conversation a request belongs to.
 *
 * A stored conversation keeps its own kind; a conversation not in the list yet
 * (a guest's unsaved chat, or a request racing creation) uses the visible workspace,
 * which is the kind it is being created with.
 */
export function resolveConversationKind(
  state: { conversations?: Conversation[]; workspace?: ConversationKind },
  conversationId: string | null | undefined,
): ConversationKind {
  const conversation = conversationId
    ? state.conversations?.find((item) => item.id === conversationId)
    : undefined;
  return conversation ? conversationKindOf(conversation) : normalizeConversationKind(state.workspace);
}

/** Whether a stored conversation belongs to the Topic Finder workspace. */
export function isTopicFinderConversation(conversation: Pick<Conversation, 'kind'> | null | undefined): boolean {
  return conversationKindOf(conversation) === TOPIC_FINDER_KIND;
}
