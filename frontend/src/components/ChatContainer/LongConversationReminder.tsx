'use client';

import { useEffect, useRef, useState } from 'react';
import { Modal } from 'antd';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';

interface LongConversationReminderProps {
  userId: string | null;
  conversationId: string | null;
  messageCount: number;
  blocked: boolean;
  onNewConversation: () => void;
}

/**
 * Offer a fresh chat at 100 messages and every three messages thereafter.
 *
 * Crossed thresholds are deferred until the chat is idle, never replayed as a
 * backlog. Browser-local high-water marks isolate accounts/conversations and
 * prevent refreshes, edits or deletions from repeating an already shown milestone.
 * Storage denial falls back to component-lifetime memory without blocking chat.
 * Only milestone/count/action metadata is logged, never identity or message text.
 */
export function LongConversationReminder({
  userId, conversationId, messageCount, blocked, onNewConversation,
}: LongConversationReminderProps) {
  const { t } = useUserPreferences();
  const seen = useRef(new Map<string, number>());
  const [pending, setPending] = useState<{ scope: string; count: number } | null>(null);
  const scope = conversationId
    ? `areqa:long-conversation-reminder:v1:${userId ?? 'guest'}:${conversationId}`
    : null;
  const previousScope = useRef(scope);

  useEffect(() => {
    // Schedule browser-storage synchronization outside the render/effect phase.
    // Cleanup prevents a stale conversation load from opening a late dialog.
    const timer = window.setTimeout(() => {
      if (previousScope.current !== scope) {
        previousScope.current = scope;
        setPending(null);
      }
      if (!scope || blocked || messageCount < 100) return;
      const milestone = 100 + Math.floor((messageCount - 100) / 3) * 3;
      let previous = seen.current.get(scope) ?? 0;
      try {
        const stored = Number(window.localStorage.getItem(scope));
        if (Number.isSafeInteger(stored) && stored >= 100 && (stored - 100) % 3 === 0) {
          previous = Math.max(previous, stored);
        }
      } catch {
        // Browser storage is optional; in-memory deduplication still applies.
      }
      if (milestone <= previous) return;
      seen.current.set(scope, milestone);
      try {
        window.localStorage.setItem(scope, String(milestone));
      } catch {
        logger.info('chat.long_conversation_reminder_storage_unavailable');
      }
      setPending({ scope, count: messageCount });
      logger.info('chat.long_conversation_reminder_shown', { milestone, messageCount });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [scope, blocked, messageCount]);

  const dismiss = () => {
    setPending(null);
    logger.info('chat.long_conversation_reminder_action', { action: 'continue' });
  };

  return (
    <Modal
      title={t('longConversationTitle')}
      open={Boolean(pending && pending.scope === scope && !blocked)}
      okText={t('newChat')}
      cancelText={t('longConversationContinue')}
      onCancel={dismiss}
      onOk={() => {
        if (blocked) return;
        setPending(null);
        logger.info('chat.long_conversation_reminder_action', { action: 'new_chat' });
        onNewConversation();
      }}
      centered
    >
      <p>{t('longConversationDescription', { count: pending?.count ?? messageCount })}</p>
    </Modal>
  );
}
