import { useEffect } from 'react';
import { db } from '@/database/db';
import type { Conversation } from '@/database/schema';
import { isStreamActive, loadMessages } from '@/services/chat';
import { COLLABORATIVE_REFRESH_INTERVAL_MS } from '@/services/collaborationSync';
import { syncService } from '@/services/syncService';
import { useChatStore } from '@/store/chat/store';
import { useConversationStore } from '@/store/conversation';
import { logger } from '@/utils/logger';

/**
 * Keep an open collaborative conversation current for owner and participants.
 *
 * Polls while the tab is visible and no answer is streaming, and reloads the
 * message list only when the stored conversation changed. When a
 * participant's access ends, the local copy is gone after the pull; the chat
 * closes it and `onAccessEnded` explains why.
 */
export function useCollaborativeRefresh(
  conversation: Pick<Conversation, 'id' | 'collaboration'> | null | undefined,
  userId: string | null,
  onAccessEnded: () => void,
): void {
  const conversationId = conversation?.collaboration ? conversation.id : null;

  useEffect(() => {
    if (!conversationId || !userId) return undefined;
    let running = false;
    let active = true;

    const tick = async () => {
      if (running || document.visibilityState !== 'visible') return;
      if (isStreamActive() || useChatStore.getState().isStreaming) return;
      running = true;
      try {
        const changed = await syncService.pullConversationMessages(conversationId, userId, { authoritative: true });
        if (!active || !changed) return;
        const conversationStore = useConversationStore.getState();
        if (!(await db.conversations.get(conversationId))) {
          logger.info('collab_refresh_access_ended', { component: 'ChatContainer', conversationId });
          await conversationStore.loadConversations(userId);
          if (useConversationStore.getState().activeConversationId === conversationId) {
            useConversationStore.getState().clearActiveConversation();
            useChatStore.getState().clearMessages();
          }
          onAccessEnded();
          return;
        }
        if (conversationStore.activeConversationId !== conversationId || isStreamActive()) return;
        await loadMessages(conversationId, { clearBeforeLoad: false });
        logger.info('collab_refresh_applied', { component: 'ChatContainer', conversationId });
      } catch (error) {
        logger.warn('collab_refresh_failed', {
          component: 'ChatContainer',
          conversationId,
          reason: error instanceof Error ? error.name : 'unknown',
        });
      } finally {
        running = false;
      }
    };

    const timer = window.setInterval(() => { void tick(); }, COLLABORATIVE_REFRESH_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [conversationId, onAccessEnded, userId]);
}
