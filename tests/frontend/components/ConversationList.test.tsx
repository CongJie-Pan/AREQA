import React from 'react';
import { render, screen } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationList } from '@/components/ConversationList';
import { useConversationStore } from '@/store/conversation';
import type { Conversation } from '@/database/schema';

vi.mock('next/image', () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} alt={props.alt ?? ''} />
  ),
}));

vi.mock('@/components/Auth', () => ({
  UserAuthUI: () => <div data-testid="auth-ui" />,
}));

vi.mock('@/services/chat', () => ({
  switchConversation: vi.fn(),
  deleteConversation: vi.fn(),
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      update: vi.fn(),
    },
  },
}));

vi.mock('@/store/mailbox', () => ({
  useMailboxStore: () => ({
    unreadCount: 0,
    fetchMails: vi.fn(),
  }),
}));

vi.mock('@/store/features', () => ({
  useFeatureStore: () => false,
}));

vi.mock('@/contexts/UserPreferencesContext', () => ({
  useUserPreferences: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        newChat: 'New chat',
        noConversations: 'No conversations',
        closeSidebar: 'Close sidebar',
        mailbox: 'Mailbox',
        conversationMenu: 'Conversation menu',
        rename: 'Rename',
        pin: 'Pin',
        unpin: 'Unpin',
        delete: 'Delete',
        renameTitle: 'Rename conversation',
        save: 'Save',
        cancel: 'Cancel',
        renamePlaceholder: 'Conversation name',
        enterConversationName: 'Enter a conversation name',
        renameSuccess: 'Renamed',
        renameFailed: 'Rename failed',
      };
      return translations[key] ?? key;
    },
  }),
}));

function conversation(overrides: Partial<Conversation>): Conversation {
  const now = new Date('2026-08-25T08:00:00.000Z');
  return {
    id: 'conversation-1',
    userId: 'user-1',
    title: '新對話',
    createdAt: now,
    updatedAt: now,
    messageCount: 1,
    lastMessagePreview: '',
    ...overrides,
  };
}

function renderConversationList() {
  return render(
    <App>
      <ConversationList />
    </App>,
  );
}

describe('ConversationList title states', () => {
  beforeEach(() => {
    useConversationStore.setState({
      conversations: [],
      activeConversationId: null,
      isLoading: false,
      error: null,
      streamingTitles: {},
    });
  });

  it('localizes legacy default conversation titles instead of showing persisted Chinese text', () => {
    useConversationStore.setState({
      conversations: [conversation({ id: 'conversation-1', title: '新對話' })],
      activeConversationId: 'conversation-1',
    });

    renderConversationList();

    expect(screen.getAllByText('New chat').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('新對話')).not.toBeInTheDocument();
  });

  it('shows a shimmer loading title while the generated title is pending', () => {
    useConversationStore.setState({
      conversations: [conversation({ id: 'conversation-1', title: '新對話' })],
      activeConversationId: 'conversation-1',
      streamingTitles: { 'conversation-1': '' },
    });

    renderConversationList();

    expect(screen.getByRole('status', { name: 'New chat' })).toBeInTheDocument();
    expect(screen.queryByText('新對話')).not.toBeInTheDocument();
  });
});
