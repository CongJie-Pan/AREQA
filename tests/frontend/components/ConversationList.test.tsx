import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationList } from '@/components/ConversationList';
import { useConversationStore } from '@/store/conversation';
import { useChatStore } from '@/store/chat';
import type { Conversation } from '@/database/schema';
import { databaseService } from '@/services/database';

vi.mock('next/image', () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} alt={props.alt ?? ''} />
  ),
}));

vi.mock('@/components/Auth', () => ({
  UserAuthUI: ({ onOpenNotes }: { onOpenNotes?: () => void }) => (
    <div data-testid="auth-ui">
      {onOpenNotes && (
        <button type="button" onClick={onOpenNotes}>
          Mock Notes
        </button>
      )}
    </div>
  ),
}));

vi.mock('@/services/chat', () => ({
  switchConversation: vi.fn(),
  deleteConversation: vi.fn(),
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      update: vi.fn(),
      getAll: vi.fn(),
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

function renderConversationList(props: Partial<React.ComponentProps<typeof ConversationList>> = {}) {
  return render(
    <App>
      <ConversationList {...props} />
    </App>,
  );
}

describe('ConversationList title states', () => {
  it('reserves logo space and omits the duplicate toggle when the shell owns it', () => {
    const { container } = render(<App><ConversationList externalSidebarToggle /></App>);
    expect(screen.queryByTitle('Close sidebar')).not.toBeInTheDocument();
    expect(container.querySelector('.areqa-conversation-logo-row-external-toggle')).toBeInTheDocument();
    expect(screen.getByAltText('AREQA Logo')).toBeInTheDocument();
  });

  beforeEach(() => {
    useConversationStore.setState({
      conversations: [],
      activeConversationId: null,
      isLoading: false,
      error: null,
      streamingTitles: {},
    });
    useChatStore.setState({
      messages: [],
      isStreaming: false,
      currentStreamingId: null,
      thinkingContent: '',
      thinkingStartTime: null,
      isThinking: false,
      currentContent: '',
      currentCitations: [],
      currentAnswerBlocks: [],
      quotedText: null,
      error: null,
      tokenUsage: null,
      useRag: false,
      useWebSearch: false,
      searchMode: 'never',
      forceThink: true,
      ragStatus: 'idle',
      ragMessage: '',
      ragSources: [],
    });
  });

  it('keeps existing rows mounted while a delayed background refresh updates their titles', async () => {
    const existing = conversation({ title: 'Existing title' });
    useConversationStore.setState({ conversations: [existing] });
    let finish!: (rows: Conversation[]) => void;
    vi.mocked(databaseService.conversation.getAll).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const { container } = renderConversationList();
    const row = container.querySelector('.areqa-conversation-item');
    let pending!: Promise<void>;
    act(() => { pending = useConversationStore.getState().loadConversations('user-1'); });
    expect(screen.getByText('Existing title')).toBeInTheDocument();
    expect(container.querySelector('.areqa-conversation-loading')).toBeNull();
    expect(container.querySelector('.areqa-conversation-item')).toBe(row);
    await act(async () => { finish([{ ...existing, title: 'Refreshed title' }]); await pending; });
    expect(screen.getByText('Refreshed title')).toBeInTheDocument();
    expect(container.querySelector('.areqa-conversation-item')).toBe(row);
  });

  it('keeps existing rows visible when a background refresh fails', async () => {
    useConversationStore.setState({ conversations: [conversation({ title: 'Cached title' })] });
    let fail!: (error: Error) => void;
    vi.mocked(databaseService.conversation.getAll).mockReturnValueOnce(new Promise((_resolve, reject) => { fail = reject; }));
    const { container } = renderConversationList();
    const row = container.querySelector('.areqa-conversation-item');
    let pending!: Promise<void>;
    act(() => { pending = useConversationStore.getState().loadConversations('user-1'); });
    expect(container.querySelector('.areqa-conversation-item')).toBe(row);
    await act(async () => { fail(new Error('Fixture refresh failure')); await pending; });
    expect(screen.getByText('Cached title')).toBeInTheDocument();
    expect(container.querySelector('.areqa-conversation-item')).toBe(row);
    expect(useConversationStore.getState().isLoading).toBe(false);
  });

  it('shows loading for an empty initial history and hides another account’s existing rows', async () => {
    useConversationStore.setState({ conversations: [conversation({ title: 'Previous account title' })] });
    let finish!: (rows: Conversation[]) => void;
    vi.mocked(databaseService.conversation.getAll).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const { container } = renderConversationList();
    let pending!: Promise<void>;
    act(() => { pending = useConversationStore.getState().loadConversations('user-2'); });
    expect(screen.queryByText('Previous account title')).not.toBeInTheDocument();
    expect(container.querySelector('.areqa-conversation-loading')).toBeInTheDocument();
    await act(async () => { finish([]); await pending; });
    expect(screen.getByText('No conversations')).toBeInTheDocument();
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

  it('shows a shimmer loading title during the first assistant stream before title generation starts', () => {
    useConversationStore.setState({
      conversations: [conversation({ id: 'conversation-1', title: '新對話' })],
      activeConversationId: 'conversation-1',
      streamingTitles: {},
    });
    useChatStore.setState({
      messages: [
        {
          id: 'user-message-1',
          userId: 'user-1',
          conversationId: 'conversation-1',
          role: 'user',
          content: 'Explain photosynthesis',
          createdAt: new Date('2026-08-25T08:00:00.000Z'),
        },
        {
          id: 'assistant-message-1',
          userId: 'user-1',
          conversationId: 'conversation-1',
          role: 'assistant',
          content: '',
          createdAt: new Date('2026-08-25T08:00:01.000Z'),
          isStreaming: true,
        },
      ],
      isStreaming: true,
      currentStreamingId: 'assistant-message-1',
    });

    renderConversationList();

    expect(screen.getByRole('status', { name: 'New chat' })).toBeInTheDocument();
    expect(screen.queryByText('新對話')).not.toBeInTheDocument();
  });

  it('opens the notes panel from the account area', () => {
    const onSelectGumPanel = vi.fn();

    renderConversationList({ onSelectGumPanel });

    fireEvent.click(screen.getByRole('button', { name: 'Mock Notes' }));

    expect(onSelectGumPanel).toHaveBeenCalledWith('notes');
  });

  it('enables title marquee only when the rendered title overflows on hover', () => {
    useConversationStore.setState({
      conversations: [
        conversation({
          id: 'conversation-long-title',
          title: 'CULTURECONVERSE跨文化多輪模擬評估框架與實驗結果分析',
        }),
      ],
      activeConversationId: 'conversation-long-title',
    });

    renderConversationList();

    const titleContainer = screen
      .getByText('CULTURECONVERSE跨文化多輪模擬評估框架與實驗結果分析')
      .closest('.areqa-conversation-item-title') as HTMLElement;

    Object.defineProperties(titleContainer, {
      clientWidth: { configurable: true, value: 120 },
      scrollWidth: { configurable: true, value: 360 },
    });

    fireEvent.pointerEnter(titleContainer);

    expect(titleContainer).toHaveAttribute('data-overflow', 'true');
    expect(titleContainer).toHaveStyle({ '--areqa-title-marquee-width': '120px' });
  });
});
