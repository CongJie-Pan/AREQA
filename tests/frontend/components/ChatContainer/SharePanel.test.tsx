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

  it('offers view-only and participate access', () => {
    const onAccessLevelChange = vi.fn();
    render(<UserPreferencesProvider><SharePanel
      user={user} isCopying={false} onCopyLink={vi.fn()} onClose={vi.fn()}
      accessLevel="view" onAccessLevelChange={onAccessLevelChange}
    /></UserPreferencesProvider>);

    expect(screen.getByRole('radio', { name: /僅檢視/ })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('radio', { name: /可參與/ }));
    expect(onAccessLevelChange).toHaveBeenCalledWith('edit');
  });

  it('lists participants with display names and lets the owner remove them', () => {
    const onRemoveMember = vi.fn();
    render(<UserPreferencesProvider><SharePanel
      user={user} isCopying={false} onCopyLink={vi.fn()} onClose={vi.fn()}
      accessLevel="edit" onAccessLevelChange={vi.fn()}
      members={[{ userId: 'm1', name: 'Mei' }, { userId: 'm2', name: null }]}
      onRemoveMember={onRemoveMember}
    /></UserPreferencesProvider>);

    expect(screen.getByText('共同對話不會使用任何人的個人學習記憶。')).toBeInTheDocument();
    expect(screen.getAllByTestId('share-member')).toHaveLength(2);
    expect(screen.getByText('Mei')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '移除' })[0]);
    expect(onRemoveMember).toHaveBeenCalledWith('m1');
  });

  it('shows participant avatars and falls back to initials for unsafe ones', () => {
    render(<UserPreferencesProvider><SharePanel
      user={user} isCopying={false} onCopyLink={vi.fn()} onClose={vi.fn()}
      accessLevel="edit" onAccessLevelChange={vi.fn()}
      members={[
        { userId: 'm1', name: 'Mei', avatarUrl: 'https://example.com/mei.png' },
        { userId: 'm2', name: 'Lin', avatarUrl: 'javascript:alert(1)' },
      ]}
    /></UserPreferencesProvider>);

    const [mei, lin] = screen.getAllByTestId('share-member');
    expect(mei.querySelector('img')).toHaveAttribute('src', 'https://example.com/mei.png');
    expect(lin.querySelector('img')).toBeNull();
    expect(lin).toHaveTextContent('L');
  });
});
