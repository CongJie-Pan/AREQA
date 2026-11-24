import { useEffect } from 'react';
import { db } from '@/database/db';
import type { Conversation } from '@/database/schema';
import { isStreamActive, loadMessages } from '@/services/chat';
import {
  COLLABORATIVE_LIST_REFRESH_INTERVAL_MS,
  COLLABORATIVE_REFRESH_INTERVAL_MS,
  syncCollaborativeConversationList,
} from '@/services/collaborationSync';
import { syncService } from '@/services/syncService';
import { useChatStore } from '@/store/chat/store';
import { useConversationStore } from '@/store/conversation';
import { logger } from '@/utils/logger';

/**
 * Keep collaborative conversations current for owner and participants.
 *
 * Two loops run while the tab is visible:
 * - The shared-conversation list is re-synced every 20 s and whenever the tab
 *   regains focus. Without it, an owner whose first participant joins after
 *   the page loaded never learns the chat is shared (the flag below is only
 *   set by a full sync), so it never refreshes until a page reload.
 * - The open collaborative conversation is polled every 5 s (and on focus),
 *   reloading the message list only when the stored conversation changed.
 *
 * When a participant's access ends, the local copy is gone after the pull;
 * the chat closes it and `onAccessEnded` explains why.
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
    const onReturn = () => { void tick(); };
    window.addEventListener('focus', onReturn);
    document.addEventListener('visibilitychange', onReturn);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', onReturn);
      document.removeEventListener('visibilitychange', onReturn);
    };
  }, [conversationId, onAccessEnded, userId]);

  useEffect(() => {
    if (!userId) return undefined;
    let running = false;
    let active = true;

    const syncList = async () => {
      if (running || document.visibilityState !== 'visible') return;
      running = true;
      try {
        if (await syncCollaborativeConversationList(userId) && active) {
          // Updates sidebar entries and the open chat's shared flag, which starts the poll above.
          await useConversationStore.getState().loadConversations(userId);
          logger.info('collab_list_refresh_applied', { component: 'ChatContainer' });
        }
      } catch (error) {
        logger.warn('collab_list_refresh_failed', {
          component: 'ChatContainer',
          reason: error instanceof Error ? error.name : 'unknown',
        });
      } finally {
        running = false;
      }
    };

    const timer = window.setInterval(() => { void syncList(); }, COLLABORATIVE_LIST_REFRESH_INTERVAL_MS);
    const onReturn = () => { void syncList(); };
    window.addEventListener('focus', onReturn);
    document.addEventListener('visibilitychange', onReturn);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', onReturn);
      document.removeEventListener('visibilitychange', onReturn);
    };
  }, [userId]);
}
