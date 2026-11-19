'use client';

import React from 'react';
import type { User } from '@supabase/supabase-js';
import { Globe, Link2, UsersRound, X } from 'lucide-react';
import { createStyles } from 'antd-style';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';

const useStyles = createStyles(({ css, token }) => ({
  panel: css`
    /* Popover adds 12px; with this padding the content sits 20px from each edge
       and the panel keeps 16px gutters on phones. */
    box-sizing: border-box;
    width: min(440px, calc(100vw - 56px));
    padding: 8px 8px 4px;
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
    margin-left: 6px;
    color: color-mix(in srgb, var(--foreground) 55%, transparent);
    font-weight: 400;
  `,
  role: css`
    flex: none;
    color: color-mix(in srgb, var(--foreground) 60%, transparent);
    font-size: 13px;
  `,
  accessOptions: css`
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0 0 12px;
  `,
  accessOption: css`
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 10px;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;

    &:hover {
      background: color-mix(in srgb, var(--foreground) 5%, transparent);
    }

    &[aria-checked='true'] {
      border-color: color-mix(in srgb, var(--foreground) 55%, transparent);
      background: color-mix(in srgb, var(--foreground) 6%, transparent);
    }

    &:disabled {
      cursor: progress;
      opacity: 0.6;
    }
  `,
  notice: css`
    margin: 4px 0 0;
    color: color-mix(in srgb, var(--foreground) 60%, transparent);
    font-size: 12px;
  `,
  removeMember: css`
    flex: none;
    padding: 4px 10px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 8px;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 12px;
    cursor: pointer;

    &:hover {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
    }
  `,
  footer: css`
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 12px;
    padding: 14px 0 4px;
    border-top: 1px solid var(--areqa-subtle-border);
  `,
  secondary: css`
    display: inline-flex;
    align-items: center;
    padding: 7px 14px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 9px;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
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
}));

function displayName(user: User): string {
  const meta = user.user_metadata ?? {};
  return String(meta.username || meta.full_name || meta.name || user.email || '');
}

export type ShareAccessLevel = 'view' | 'edit';

export interface ShareMember {
  userId: string;
  name?: string | null;
}

/**
 * Share dialog body: link access, who has access, and a Copy link action.
 *
 * Copying creates or refreshes the link with the chosen access. A view-only
 * link moves its snapshot to "now"; a participate link lets signed-in people
 * join the whole conversation. Switching back to view-only removes every
 * participant's access immediately.
 */
export function SharePanel({
  user, isCopying, onCopyLink, onClose,
  accessLevel = 'view', onAccessLevelChange, members = [], onRemoveMember, onOpenCollab,
}: {
  user: User;
  isCopying: boolean;
  onCopyLink: () => void;
  onClose: () => void;
  accessLevel?: ShareAccessLevel;
  onAccessLevelChange?: (level: ShareAccessLevel) => void;
  members?: ShareMember[];
  onRemoveMember?: (userId: string) => void;
  onOpenCollab?: () => void;
}) {
  const { styles, cx } = useStyles();
  const { t } = useUserPreferences();
  const name = displayName(user);
  const avatarUrl = user.user_metadata?.avatar_url || user.user_metadata?.picture;
  const isEdit = accessLevel === 'edit';

  const accessOption = (level: ShareAccessLevel, icon: React.ReactNode, title: string, hint: string) => (
    <button
      type="button"
      role="radio"
      aria-checked={accessLevel === level}
      className={styles.accessOption}
      disabled={isCopying}
      onClick={() => onAccessLevelChange?.(level)}
    >
      <span className={styles.rowIcon} aria-hidden="true">{icon}</span>
      <span className={styles.rowText}>
        <span className={styles.rowTitle}>{title}</span>
        <span className={styles.rowMeta}>{hint}</span>
      </span>
    </button>
  );

  return (
    <div className={styles.panel} role="dialog" aria-label={t('shareDialogTitle')}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t('shareDialogTitle')}</h2>
        <button type="button" className={styles.close} aria-label={t('shareDialogClose')} onClick={onClose}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <p className={styles.subtitle}>{isEdit ? t('collabMemoryNotice') : t('shareSnapshotNotice')}</p>

      {onAccessLevelChange && (
        <>
          <p className={styles.sectionLabel}>{t('shareAccessLabel')}</p>
          <div className={styles.accessOptions} role="radiogroup" aria-label={t('shareAccessLabel')}>
            {accessOption('view', <Globe size={17} />, t('shareAccessView'), t('shareAccessViewHint'))}
            {accessOption('edit', <UsersRound size={17} />, t('shareAccessEdit'), t('shareAccessEditHint'))}
          </div>
        </>
      )}

      <p className={styles.sectionLabel}>{t('shareWhoHasAccess')}</p>
      {!onAccessLevelChange && (
        <div className={styles.row}>
          <span className={styles.rowIcon} aria-hidden="true"><Globe size={17} /></span>
          <span className={styles.rowText}>
            <span className={styles.rowTitle}>{t('shareAnyoneWithLink')}</span>
            <span className={styles.rowMeta}>{t('shareAnyoneWithLinkHint')}</span>
          </span>
        </div>
      )}
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
      {isEdit && members.map((member) => {
        const memberName = member.name?.trim() || t('shareMemberUnnamed');
        return (
          <div className={styles.row} key={member.userId} data-testid="share-member">
            <span className={cx(styles.rowIcon, styles.avatar)} aria-hidden="true">
              {memberName[0]?.toUpperCase() ?? '?'}
            </span>
            <span className={styles.rowText}>
              <span className={styles.rowTitle}>{memberName}</span>
              <span className={styles.rowMeta}>{t('shareEditorRole')}</span>
            </span>
            {onRemoveMember && (
              <button type="button" className={styles.removeMember} onClick={() => onRemoveMember(member.userId)}>
                {t('shareMemberRemove')}
              </button>
            )}
          </div>
        );
      })}

      <div className={styles.footer}>
        {isEdit && onOpenCollab && (
          <button type="button" className={styles.secondary} onClick={onOpenCollab}>
            {t('shareOpenCollab')}
          </button>
        )}
        <button type="button" className={styles.copy} disabled={isCopying} onClick={onCopyLink}>
          <Link2 size={16} aria-hidden="true" />
          {t('shareCopyLink')}
        </button>
      </div>
    </div>
  );
}
