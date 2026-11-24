'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { createStyles } from 'antd-style';
import { safeAvatarUrl } from '@/utils/avatarUrl';

const useStyles = createStyles(({ css }) => ({
  avatar: css`
    position: absolute;
    top: -10px;
    right: -10px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    overflow: hidden;
    border: 2px solid var(--background);
    border-radius: 50%;
    background: #c8467a;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    line-height: 1;
    cursor: default;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    &:focus-visible {
      outline: 2px solid var(--foreground);
      outline-offset: 1px;
    }
  `,
}));

/**
 * Asker's avatar on a user bubble in a collaborative conversation; hovering or
 * focusing it shows who asked.
 */
export function AuthorAvatar({ label, name, avatarUrl }: { label: string; name: string; avatarUrl?: string | null }) {
  const { styles } = useStyles();
  const src = safeAvatarUrl(avatarUrl);
  return (
    <Tooltip title={label}>
      <span className={styles.avatar} role="img" aria-label={label} tabIndex={0} data-testid="message-author-avatar">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {src ? <img src={src} alt="" referrerPolicy="no-referrer" /> : (name.trim()[0] || '?').toUpperCase()}
      </span>
    </Tooltip>
  );
}
