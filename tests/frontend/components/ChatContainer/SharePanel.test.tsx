import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@supabase/supabase-js';
import { SharePanel } from '../../../../frontend/src/components/ChatContainer/SharePanel';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';

const user = { id: 'u1', email: 'owner@example.com', user_metadata: { username: 'CongJie-Pan' } } as unknown as User;

describe('SharePanel', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('explains the snapshot, link access and owner, without invitations', () => {
    render(<UserPreferencesProvider><SharePanel user={user} isCopying={false} onCopyLink={vi.fn()} onClose={vi.fn()} /></UserPreferencesProvider>);

    expect(screen.getByRole('dialog', { name: '分享對話' })).toBeInTheDocument();
    expect(screen.getByText('只會分享到目前為止的訊息')).toBeInTheDocument();
    expect(screen.getByText('擁有連結的任何人')).toBeInTheDocument();
    expect(screen.getByText('CongJie-Pan')).toBeInTheDocument();
    expect(screen.getByText('owner@example.com')).toBeInTheDocument();
    expect(screen.getByText('擁有者')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/email/i)).not.toBeInTheDocument();
  });

  it('copies the link and closes on request', () => {
    const onCopyLink = vi.fn();
    const onClose = vi.fn();
    render(<UserPreferencesProvider><SharePanel user={user} isCopying={false} onCopyLink={onCopyLink} onClose={onClose} /></UserPreferencesProvider>);

    fireEvent.click(screen.getByRole('button', { name: '複製連結' }));
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onCopyLink).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('disables copying while a link is being created', () => {
    render(<UserPreferencesProvider><SharePanel user={user} isCopying onCopyLink={vi.fn()} onClose={vi.fn()} /></UserPreferencesProvider>);
    expect(screen.getByRole('button', { name: '複製連結' })).toBeDisabled();
  });
});
