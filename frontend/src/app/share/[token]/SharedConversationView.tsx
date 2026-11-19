'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { SharedMessages, type SharedConversation } from '@/components/SharedConversation';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { initializeAuth, useAuthStore } from '@/store/auth';
import styles from './styles.module.css';

export type { SharedConversation, SharedMessage } from '@/components/SharedConversation';

/**
 * Public, signed-out view of a shared conversation.
 *
 * Signed-in visitors are moved into their own AREQA workspace
 * (`/?share=<token>`), where the same read-only messages render inside the app
 * shell; owners there also get an "Open original chat" bar.
 */
export function SharedConversationView({ conversation, token }: { conversation: SharedConversation; token?: string }) {
  const user = useAuthStore((state) => state.user);
  const isAuthReady = useAuthStore((state) => state.isInitialized);
  const { t } = useUserPreferences();

  useEffect(() => {
    if (token) void initializeAuth();
  }, [token]);

  useEffect(() => {
    if (token && isAuthReady && user) window.location.replace(`/?share=${encodeURIComponent(token)}`);
  }, [isAuthReady, token, user]);

  return (
    <main className={styles.page}>
      <section className={styles.chat}>
        <header className={styles.header}>
          <div className={styles.headerInner}>
            <div className={styles.brand}>AREQA</div>
            <h1>{conversation.title || 'Shared conversation'}</h1>
          </div>
        </header>
        <SharedMessages conversation={conversation} className={styles.messages} />
        {/* Joining needs an account; signed-in visitors are moved into the app shell above. */}
        {conversation.accessLevel === 'edit' && (
          <div className="areqa-shared-owner-bar" role="note">
            <span className="areqa-shared-owner-bar-text">{t('collabLoginToJoin')}</span>
            <Link className="areqa-shared-owner-bar-action" href="/">{t('collabBack')}</Link>
          </div>
        )}
      </section>
    </main>
  );
}
