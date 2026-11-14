'use client';

import { useEffect, useRef, useState } from 'react';
import { useStyles } from './styles';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';

interface LongConversationReminderProps {
  userId: string | null;
  conversationId: string | null;
  replyCount: number;
  blocked: boolean;
  canCreateBranch?: boolean;
  onNewConversation: () => void;
}

/**
 * Offer ways to continue at 100 assistant replies and every five replies thereafter.
 *
 * Crossed thresholds are deferred until the chat is idle, never replayed as a
 * backlog. Browser-local high-water marks isolate accounts/conversations and
 * prevent refreshes, edits or deletions from repeating an already shown milestone.
 * Storage denial falls back to component-lifetime memory without blocking chat.
 * Only milestone/count/action metadata is logged, never identity or message text.
 */
export function LongConversationReminder({
  userId, conversationId, replyCount, blocked, canCreateBranch = false, onNewConversation,
}: LongConversationReminderProps) {
  const { t } = useUserPreferences();
  const { styles } = useStyles();
  const seen = useRef(new Map<string, number>());
  const [pending, setPending] = useState<{ scope: string; count: number } | null>(null);
  const scope = conversationId
    ? `areqa:long-conversation-reminder:v2:assistant:${userId ?? 'guest'}:${conversationId}`
    : null;
  const previousScope = useRef(scope);

  useEffect(() => {
    // Schedule browser-storage synchronization outside the render/effect phase.
    // Cleanup prevents a stale conversation load from opening a late reminder.
    const timer = window.setTimeout(() => {
      if (previousScope.current !== scope) {
        previousScope.current = scope;
        setPending(null);
      }
      if (!scope || blocked || replyCount < 100) return;
      const milestone = 100 + Math.floor((replyCount - 100) / 5) * 5;
      let previous = seen.current.get(scope) ?? 0;
      try {
        const stored = Number(window.localStorage.getItem(scope));
        if (Number.isSafeInteger(stored) && stored >= 100 && (stored - 100) % 5 === 0) {
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
      setPending({ scope, count: replyCount });
      logger.info('chat.long_conversation_reminder_shown', { milestone, replyCount });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [scope, blocked, replyCount]);

  const dismiss = () => {
    setPending(null);
    logger.info('chat.long_conversation_reminder_action', { action: 'continue' });
  };

  if (!pending || pending.scope !== scope || blocked || replyCount < 100) return null;

  return (
    <aside className={styles.longConversationReminder} role="status" aria-live="polite">
      <div>
        <strong>{t('longConversationTitle')}</strong>
        <p>{t(canCreateBranch ? 'longConversationBranchDescription' : 'longConversationDescription', { count: pending.count })}</p>
      </div>
      <div className={styles.longConversationReminderActions}>
        <button
          type="button"
          onClick={() => {
            setPending(null);
            logger.info('chat.long_conversation_reminder_action', { action: 'new_chat' });
            onNewConversation();
          }}
        >
          {t('newChat')}
        </button>
        <button type="button" onClick={dismiss}>{t('longConversationContinue')}</button>
      </div>
    </aside>
  );
}
