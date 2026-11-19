'use client';

/**
 * Read-only rendering of a shared conversation.
 *
 * Every share surface (public page, signed-in app shell, owner preview) renders
 * messages with the chat's own `MessageItem` and `MessageList` styles, so the
 * shared copy looks exactly like the original chat instead of drifting from a
 * separate renderer.
 */
import React, { useMemo, useState } from 'react';
import { Info, UsersRound } from 'lucide-react';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import type { CitationSource } from '@/components/Citations';
import type { AnswerBlock } from '@/database/schema';
import type { DisplayMessage } from '@/store/chat/types';
import { normalizeAttachmentMetadata } from '@/utils/attachments';
import { MessageItem } from '@/components/MessageList/MessageItem';
import { useStyles } from '@/components/MessageList/styles';

export interface SharedMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: string[] | null;
  sources?: unknown;
  answerBlocks?: unknown;
  attachments?: unknown;
  stoppedByUser?: boolean | null;
  /** Collaborative conversations only: who wrote the message. */
  authorUserId?: string | null;
  authorName?: string | null;
  createdAt: string;
}

export interface SharedConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  /** Snapshot cutoff; null for shares created before snapshots existed. */
  sharedAt?: string | null;
  /** 'edit' links let signed-in visitors join the live conversation. */
  accessLevel?: 'view' | 'edit';
  messages: SharedMessage[];
}

function arrayOrUndefined<T>(value: unknown): T[] | undefined {
  return Array.isArray(value) && value.length > 0 ? value as T[] : undefined;
}

/** Map the public share payload onto the chat's display message shape. */
export function toSharedDisplayMessages(conversation: SharedConversation): DisplayMessage[] {
  return conversation.messages
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .map((message) => {
      const attachments = normalizeAttachmentMetadata(message.attachments);
      return {
        id: message.id,
        userId: '',
        conversationId: conversation.id,
        role: message.role,
        content: typeof message.content === 'string' ? message.content : '',
        createdAt: new Date(message.createdAt),
        ...(attachments.length > 0 ? { attachments } : {}),
        ...(arrayOrUndefined<string>(message.citations) ? { citations: message.citations as string[] } : {}),
        ...(arrayOrUndefined<CitationSource>(message.sources) ? { sources: message.sources as CitationSource[] } : {}),
        ...(arrayOrUndefined<AnswerBlock>(message.answerBlocks) ? { answerBlocks: message.answerBlocks as AnswerBlock[] } : {}),
        ...(message.stoppedByUser ? { stoppedByUser: true } : {}),
      } as DisplayMessage;
    });
}

export function SharedMessages({
  conversation, className, authorLabel,
}: {
  conversation: SharedConversation;
  className?: string;
  /** Collaborative view: label shown above each user message (who asked). */
  authorLabel?: (message: SharedMessage) => string | null;
}) {
  const { styles, cx } = useStyles();
  const messages = useMemo(() => toSharedDisplayMessages(conversation), [conversation]);
  const sourceById = useMemo(
    () => new Map(conversation.messages.map((message) => [message.id, message])),
    [conversation],
  );

  return (
    <div className={cx('areqa-message-list-viewport', styles.viewport, className)}>
      <div
        className={cx('areqa-message-list', 'areqa-message-list-non-empty', styles.container, styles.nonEmpty)}
        data-testid="shared-messages"
      >
        {messages.map((message, index) => {
          const source = sourceById.get(message.id);
          const label = authorLabel && message.role === 'user' && source ? authorLabel(source) : null;
          return (
            <React.Fragment key={message.id}>
              {label && <div className="areqa-collab-author" data-testid="collab-author">{label}</div>}
              <MessageItem
                message={message}
                isLast={index === messages.length - 1}
                readOnly
                className={cx(
                  message.role === 'assistant' && index > 0 && messages[index - 1].role === 'user' && 'assistant-after-user',
                )}
              />
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Bottom bar shown to the owner instead of the composer, as in Claude's shared
 * copies: the page is read-only and the original chat is one click away.
 */
export function SharedOwnerBar({ onOpenOriginal }: { onOpenOriginal?: () => void }) {
  const { t } = useUserPreferences();
  return (
    <div className="areqa-shared-owner-bar" role="note">
      <Info size={16} aria-hidden="true" />
      <span className="areqa-shared-owner-bar-text">{t('shareReadOnlyOwnerNotice')}</span>
      {onOpenOriginal && (
        <button type="button" className="areqa-shared-owner-bar-action" onClick={onOpenOriginal}>
          {t('shareOpenOriginal')}
        </button>
      )}
    </div>
  );
}

/**
 * Bottom bar for signed-in visitors of an edit link: joining adds them as a
 * participant and opens the collaborative page for the whole conversation.
 */
export function SharedJoinBar({ token }: { token: string }) {
  const { t } = useUserPreferences();
  const [isJoining, setIsJoining] = useState(false);
  const [failed, setFailed] = useState(false);

  const join = async () => {
    setIsJoining(true);
    setFailed(false);
    try {
      const response = await authenticatedFetch('/api/collab/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const payload = await response.json().catch(() => null) as { conversationId?: string } | null;
      if (!response.ok || !payload?.conversationId) throw new Error(`join_failed_${response.status}`);
      logger.info('collab_join_succeeded', { component: 'SharedJoinBar' });
      window.location.assign(`/collab/${payload.conversationId}`);
    } catch {
      logger.warn('collab_join_failed', { component: 'SharedJoinBar' });
      setFailed(true);
      setIsJoining(false);
    }
  };

  return (
    <div className="areqa-shared-owner-bar" role="note">
      <UsersRound size={16} aria-hidden="true" />
      <span className="areqa-shared-owner-bar-text">
        {failed ? t('collabJoinFailed') : t('collabJoinNotice')}
      </span>
      <button
        type="button"
        className="areqa-shared-owner-bar-action"
        disabled={isJoining}
        onClick={() => { void join(); }}
      >
        {t('collabJoin')}
      </button>
    </div>
  );
}
