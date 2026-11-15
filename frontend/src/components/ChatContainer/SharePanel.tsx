'use client';

import React from 'react';
import type { User } from '@supabase/supabase-js';
import { Globe, Link2, X } from 'lucide-react';
import { createStyles } from 'antd-style';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';

const useStyles = createStyles(({ css, token }) => ({
  panel: css`
    width: min(440px, calc(100vw - 32px));
    color: var(--foreground);
  `,
  header: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  `,
  title: css`
    margin: 0;
    font-size: 16px;
    font-weight: 650;
  `,
  close: css`
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: color-mix(in srgb, var(--foreground) 75%, transparent);
    cursor: pointer;

    &:hover {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
    }
  `,
  subtitle: css`
    margin: 6px 0 16px;
    color: color-mix(in srgb, var(--foreground) 60%, transparent);
    font-size: 13px;
  `,
  sectionLabel: css`
    margin: 0 0 8px;
    color: color-mix(in srgb, var(--foreground) 60%, transparent);
    font-size: 12px;
  `,
  row: css`
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
  `,
  rowIcon: css`
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--foreground) 8%, transparent);
    color: color-mix(in srgb, var(--foreground) 80%, transparent);
  `,
  avatar: css`
    background: #c8467a;
    color: #ffffff;
    font-weight: 700;
    overflow: hidden;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
  `,
  rowText: css`
    display: flex;
    flex: 1;
    min-width: 0;
    flex-direction: column;
    line-height: 1.35;
  `,
  rowTitle: css`
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
    font-weight: 600;
  `,
  rowMeta: css`
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: color-mix(in srgb, var(--foreground) 55%, transparent);
    font-size: 12px;
  `,
  you: css`
    margin-left: 4px;
    color: color-mix(in srgb, var(--foreground) 55%, transparent);
    font-weight: 400;
  `,
  role: css`
    flex: none;
    color: color-mix(in srgb, var(--foreground) 60%, transparent);
    font-size: 13px;
  `,
  footer: css`
    display: flex;
    justify-content: flex-end;
    margin-top: 12px;
    padding-top: 14px;
    border-top: 1px solid var(--areqa-subtle-border);
  `,
  copy: css`
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    border: 0;
    border-radius: 9px;
    background: ${token.colorText};
    color: var(--background);
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;

    &:disabled {
      opacity: 0.6;
      cursor: progress;
    }
  `,
  note: css`
    margin: 10px 0 0;
    color: color-mix(in srgb, var(--foreground) 50%, transparent);
    font-size: 12px;
  `,
}));

function displayName(user: User): string {
  const meta = user.user_metadata ?? {};
  return String(meta.username || meta.full_name || meta.name || user.email || '');
}

/**
 * Share dialog body: who can open the link and a Copy link action.
 *
 * Sharing is link-based (no invitations yet): copying creates or refreshes the
 * link and moves its snapshot to "now", so only messages up to this moment are
 * visible through it.
 */
export function SharePanel({
  user, isCopying, onCopyLink, onClose,
}: { user: User; isCopying: boolean; onCopyLink: () => void; onClose: () => void }) {
  const { styles, cx } = useStyles();
  const { t } = useUserPreferences();
  const name = displayName(user);
  const avatarUrl = user.user_metadata?.avatar_url || user.user_metadata?.picture;

  return (
    <div className={styles.panel} role="dialog" aria-label={t('shareDialogTitle')}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t('shareDialogTitle')}</h2>
        <button type="button" className={styles.close} aria-label={t('shareDialogClose')} onClick={onClose}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <p className={styles.subtitle}>{t('shareSnapshotNotice')}</p>

      <p className={styles.sectionLabel}>{t('shareWhoHasAccess')}</p>
      <div className={styles.row}>
        <span className={styles.rowIcon} aria-hidden="true"><Globe size={17} /></span>
        <span className={styles.rowText}>
          <span className={styles.rowTitle}>{t('shareAnyoneWithLink')}</span>
          <span className={styles.rowMeta}>{t('shareAnyoneWithLinkHint')}</span>
        </span>
      </div>
      <div className={styles.row}>
        <span className={cx(styles.rowIcon, styles.avatar)} aria-hidden="true">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {avatarUrl ? <img src={String(avatarUrl)} alt="" /> : (name.trim()[0] || '?').toUpperCase()}
        </span>
        <span className={styles.rowText}>
          <span className={styles.rowTitle}>
            {name}
            <span className={styles.you}>{t('shareYou')}</span>
          </span>
          {user.email && user.email !== name && <span className={styles.rowMeta}>{user.email}</span>}
        </span>
        <span className={styles.role}>{t('shareOwnerRole')}</span>
      </div>

      <div className={styles.footer}>
        <button type="button" className={styles.copy} disabled={isCopying} onClick={onCopyLink}>
          <Link2 size={16} aria-hidden="true" />
          {t('shareCopyLink')}
        </button>
      </div>
      <p className={styles.note}>{t('shareLinkAccessNote')}</p>
    </div>
  );
}
