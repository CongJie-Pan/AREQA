import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import type { User } from '@supabase/supabase-js';
import { MessageItem } from '../../../../frontend/src/components/MessageList/MessageItem';
import { AuthorAvatar } from '../../../../frontend/src/components/MessageList/AuthorAvatar';
import { collaborativeAuthor } from '../../../../frontend/src/components/MessageList';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';
import type { DisplayMessage } from '../../../../frontend/src/store/chat/types';

const viewer = { id: 'me', user_metadata: { full_name: 'Jay', avatar_url: 'https://example.com/me.png' } } as unknown as User;

const wrap = (ui: React.ReactElement) => render(<UserPreferencesProvider><App>{ui}</App></UserPreferencesProvider>);

function message(role: 'user'): DisplayMessage {
  return {
    id: `m-${role}`, userId: 'me', conversationId: 'c1', role, content: `${role} text`,
    createdAt: new Date('2026-11-24T00:00:00Z'),
  } as DisplayMessage;
}

describe('collaborativeAuthor', () => {
  it('names another participant from the shared history', () => {
    expect(collaborativeAuthor(
      { author: { userId: 'mei', name: 'Mei', avatarUrl: 'https://example.com/mei.png' } }, viewer, '參與者', '(你)',
    )).toEqual({ name: 'Mei', avatarUrl: 'https://example.com/mei.png', label: 'Mei' });
  });

  it('treats unsynced and own messages as the viewer', () => {
    expect(collaborativeAuthor({}, viewer, '參與者', '(你)'))
      .toEqual({ name: 'Jay', avatarUrl: 'https://example.com/me.png', label: 'Jay (你)' });
    expect(collaborativeAuthor({ author: { userId: 'me', name: null } }, viewer, '參與者', '(你)').label).toBe('Jay (你)');
  });

  it('falls back to a generic name without leaking the viewer profile', () => {
    expect(collaborativeAuthor({ author: { userId: 'anon', name: null } }, viewer, '參與者', '(你)'))
      .toEqual({ name: '參與者', avatarUrl: null, label: '參與者' });
  });
});

describe('AuthorAvatar', () => {
  beforeEach(() => window.localStorage.setItem('areqa:interface-language', 'zh-TW'));

  it('shows the picture and names the asker on hover', async () => {
    wrap(<AuthorAvatar label="Mei" name="Mei" avatarUrl="https://example.com/mei.png" />);
    const avatar = screen.getByRole('img', { name: 'Mei' });
    expect(avatar.querySelector('img')).toHaveAttribute('src', 'https://example.com/mei.png');
    fireEvent.mouseEnter(avatar);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Mei');
  });

  it('uses the initial for unsafe or missing pictures', () => {
    wrap(<AuthorAvatar label="mei" name="mei" avatarUrl="javascript:alert(1)" />);
    const avatar = screen.getByRole('img', { name: 'mei' });
    expect(avatar.querySelector('img')).toBeNull();
    expect(avatar).toHaveTextContent('M');
  });
});

describe('MessageItem author avatar', () => {
  beforeEach(() => window.localStorage.setItem('areqa:interface-language', 'zh-TW'));

  it('appears on a user bubble when an author is given', () => {
    wrap(<MessageItem message={message('user')} authorName="Mei" authorLabel="Mei" readOnly />);
    expect(screen.getByTestId('message-author-avatar')).toHaveAccessibleName('Mei');
  });

  it('never appears in ordinary chats', () => {
    wrap(<MessageItem message={message('user')} readOnly />);
    expect(screen.queryByTestId('message-author-avatar')).not.toBeInTheDocument();
  });
});
