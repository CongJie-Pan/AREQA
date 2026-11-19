'use client';

/**
 * Read-only rendering of a shared conversation.
 *
 * Every share surface (public page, signed-in app shell, owner preview) renders
 * messages with the chat's own `MessageItem` and `MessageList` styles, so the
 * shared copy looks exactly like the original chat instead of drifting from a
 * separate renderer.
 */
import React, { useMemo } from 'react';
import { Info } from 'lucide-react';
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
  createdAt: string;
}

export interface SharedConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  /** Snapshot cutoff; null for shares created before snapshots existed. */
  sharedAt?: string | null;
  /** 'edit' links let signed-in visitors join the conversation. */
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

export function SharedMessages({ conversation, className }: { conversation: SharedConversation; className?: string }) {
  const { styles, cx } = useStyles();
  const messages = useMemo(() => toSharedDisplayMessages(conversation), [conversation]);

  return (
    <div className={cx('areqa-message-list-viewport', styles.viewport, className)}>
      <div
        className={cx('areqa-message-list', 'areqa-message-list-non-empty', styles.container, styles.nonEmpty)}
        data-testid="shared-messages"
      >
        {messages.map((message, index) => (
          <MessageItem
            key={message.id}
            message={message}
            isLast={index === messages.length - 1}
            readOnly
            className={cx(
              message.role === 'assistant' && index > 0 && messages[index - 1].role === 'user' && 'assistant-after-user',
            )}
          />
        ))}
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
