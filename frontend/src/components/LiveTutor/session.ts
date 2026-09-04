import type { DisplayMessage } from '@/store/chat';

/**
 * Selects the conversation that a new Live Tutor session must own.
 *
 * The active conversation is authoritative. The rendered message fallback
 * covers the brief handoff window where messages are visible before the
 * conversation store finishes selecting their conversation.
 *
 * @param activeConversationId - Current conversation selected by the app.
 * @param messages - Messages currently rendered in the chat surface.
 * @returns The conversation id to bind, or `null` when a new one is required.
 */
export function selectLiveTutorConversationId(
  activeConversationId: string | null | undefined,
  messages: DisplayMessage[],
): string | null {
  if (activeConversationId) return activeConversationId;

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const conversationId = messages[index]?.conversationId;
    if (conversationId) return conversationId;
  }

  return null;
}

/**
 * Returns only messages owned by the session-bound conversation.
 *
 * @param messages - Messages currently available in the chat store.
 * @param conversationId - Immutable conversation id for the voice session.
 * @returns Messages safe to expose to the Realtime context bridge.
 */
export function selectLiveTutorMessages(
  messages: DisplayMessage[],
  conversationId: string,
): DisplayMessage[] {
  return messages.filter((message) => message.conversationId === conversationId);
}
