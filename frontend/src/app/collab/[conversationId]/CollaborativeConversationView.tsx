'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { SharedMessages, type SharedMessage } from '@/components/SharedConversation';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { initializeAuth, useAuthStore } from '@/store/auth';
import { useCollaborativeConversation } from './useCollaborativeConversation';
import styles from './styles.module.css';

/**
 * Collaborative conversation page: the owner and joined participants read the
 * whole conversation and ask the AI in the same thread. Personal memory is
 * never used here; the backend enforces that per turn.
 */
export function CollaborativeConversationView({ conversationId }: { conversationId: string }) {
  const { t } = useUserPreferences();
  const user = useAuthStore((state) => state.user);
  const isAuthReady = useAuthStore((state) => state.isInitialized);
  const [input, setInput] = useState('');

  useEffect(() => { void initializeAuth(); }, []);

  const {
    status, conversation, draft, isSending, notice, send, refresh, leave,
  } = useCollaborativeConversation(conversationId, isAuthReady && Boolean(user));

  const displayed = useMemo(() => {
    if (!conversation) return null;
    return draft ? { ...conversation, messages: [...conversation.messages, draft] } : conversation;
  }, [conversation, draft]);

  const authorLabel = (message: SharedMessage) => {
    if (message.authorUserId && message.authorUserId === conversation?.viewerUserId) {
      return message.authorName?.trim() ? `${message.authorName.trim()} ${t('shareYou')}` : t('shareYou');
    }
    return message.authorName?.trim() || t('shareMemberUnnamed');
  };

  const submit = async () => {
    const text = input;
    if (!text.trim() || isSending) return;
    setInput('');
    // Keep the question when it was never stored, so nothing typed is lost.
    if (!await send(text)) setInput(text);
  };

  const handleLeave = async () => {
    if (await leave()) window.location.assign('/');
  };

  let body: React.ReactNode;
  if (!isAuthReady || (user && status === 'loading')) {
    body = <p className={styles.state}>{t('collabLoading')}</p>;
  } else if (!user) {
    body = <p className={styles.state}>{t('collabLoginRequired')}</p>;
  } else if (status === 'no_access') {
    body = <p className={styles.state}>{t('collabNoAccess')}</p>;
  } else if (status === 'error' || !displayed) {
    body = <p className={styles.state}>{t('collabSendFailed')}</p>;
  } else {
    body = <SharedMessages conversation={displayed} className={styles.messages} authorLabel={authorLabel} />;
  }

  const canSend = status === 'ready' && Boolean(conversation) && Boolean(user);

  return (
    <main className={styles.page}>
      <section className={styles.chat}>
        <header className={styles.header}>
          <div className={styles.headerInner}>
            <div className={styles.headerText}>
              <div className={styles.brand}>AREQA</div>
              <h1>{conversation?.title || t('collabTitleFallback')}</h1>
              <p className={styles.memoryNotice}>{t('collabMemoryNotice')}</p>
            </div>
            {canSend && (
              <button type="button" className={styles.headerAction} onClick={() => { void refresh(); }}>
                {t('collabRefresh')}
              </button>
            )}
            {canSend && conversation?.viewerRole === 'editor' && (
              <button type="button" className={styles.headerAction} onClick={() => { void handleLeave(); }}>
                {t('collabLeave')}
              </button>
            )}
            <Link className={styles.headerAction} href="/">{t('collabBack')}</Link>
          </div>
        </header>

        {body}

        {canSend && (
          <>
            {(isSending || notice) && (
              <p className={styles.status} role="status">
                {notice ? <span className={styles.error}>{t(notice)}</span> : t('collabGenerating')}
              </p>
            )}
            <form
              className={styles.composer}
              onSubmit={(event) => { event.preventDefault(); void submit(); }}
            >
              <textarea
                aria-label={t('collabPlaceholder')}
                placeholder={t('collabPlaceholder')}
                rows={1}
                value={input}
                disabled={isSending}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    void submit();
                  }
                }}
              />
              <button type="submit" className={styles.send} disabled={isSending || !input.trim()}>
                {t('collabSend')}
              </button>
            </form>
          </>
        )}
      </section>
    </main>
  );
}
