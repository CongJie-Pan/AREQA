import React from 'react';
import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatContainer } from '@/components/ChatContainer';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { databaseService } from '@/services/database';

const {
  TEST_USER_ID,
  TEST_CONVERSATION_ID,
  PREVIOUS_USER_MESSAGE,
  PREVIOUS_ASSISTANT_MESSAGE,
  LATEST_USER_MESSAGE,
  LATEST_ASSISTANT_MESSAGE,
} = vi.hoisted(() => ({
  TEST_USER_ID: 'user-integration',
  TEST_CONVERSATION_ID: 'conversation-integration',
  PREVIOUS_USER_MESSAGE: '上一輪問題',
  PREVIOUS_ASSISTANT_MESSAGE: '上一輪回答',
  LATEST_USER_MESSAGE: '最新問題',
  LATEST_ASSISTANT_MESSAGE: '最新回答',
}));

const authState = {
  user: { id: TEST_USER_ID },
  isInitialized: true,
  validateSession: vi.fn().mockResolvedValue(true),
};

vi.mock('@/store/auth', () => ({
  initializeAuth: vi.fn().mockResolvedValue(undefined),
  useAuthStore: Object.assign(
    (selector: (state: typeof authState) => unknown) => selector(authState),
    { getState: () => authState },
  ),
}));

vi.mock('@/database/db', () => ({
  getCurrentUserId: vi.fn(() => TEST_USER_ID),
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      clearGuestData: vi.fn().mockResolvedValue(undefined),
      getAll: vi.fn().mockResolvedValue([]),
    },
    message: {
      deleteManyByConversationId: vi.fn().mockResolvedValue(undefined),
      updateFeedback: vi.fn().mockResolvedValue(undefined),
    },
  },
}));

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return {
    ...actual,
    sendMessage: vi.fn().mockResolvedValue({ completed: true }),
    initializeChatService: vi.fn().mockResolvedValue(undefined),
    cancelCurrentStream: vi.fn().mockResolvedValue(undefined),
    regenerateMessage: vi.fn().mockResolvedValue(undefined),
    editUserMessage: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('@/services/syncService', () => ({
  syncService: {
    pullFromCloud: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { user: { id: TEST_USER_ID } } } }),
      getUser: vi.fn().mockResolvedValue({ data: { user: { id: TEST_USER_ID } }, error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  },
}));

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn(),
  },
}));

vi.mock('@/components/ConversationList', () => ({
  ConversationList: () => <div data-testid="conversation-list" />,
}));

vi.mock('@/components/ChatInput', () => ({
  ChatInput: () => <div data-testid="chat-input" />,
}));

vi.mock('@/components/TextSelectionToolbar', () => ({ TextSelectionToolbar: () => null }));
vi.mock('@/components/GumPanel', () => ({ GumPanel: () => null }));
vi.mock('@/components/MailboxPanel', () => ({ MailboxPanel: () => null }));
vi.mock('@/components/ProactiveManager', () => ({ ProactiveManager: () => null }));
vi.mock('@/components/LiveTutor', () => ({ LiveTutorPanel: () => null }));
vi.mock('@/utils/exportChat', () => ({
  exportToMarkdown: vi.fn(),
  exportToDocx: vi.fn(),
  exportToPdf: vi.fn(),
}));

describe('Latest turn deletion integration flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { id: TEST_USER_ID };
    authState.isInitialized = true;
    useConversationStore.setState({
      conversations: [{
        id: TEST_CONVERSATION_ID,
        userId: TEST_USER_ID,
        title: 'Integration conversation',
        createdAt: new Date('2026-09-09T00:00:00.000Z'),
        updatedAt: new Date('2026-09-09T00:00:03.000Z'),
        messageCount: 4,
        lastMessagePreview: LATEST_ASSISTANT_MESSAGE,
      }],
      activeConversationId: TEST_CONVERSATION_ID,
      isLoading: false,
      isMessageHandoffLoading: false,
      error: null,
      streamingTitles: {},
    });
    useChatStore.getState().resetStreamingState();
    useChatStore.setState({
      messages: [
        {
          id: 'user-previous',
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'user',
          content: PREVIOUS_USER_MESSAGE,
          createdAt: new Date('2026-09-09T00:00:00.000Z'),
        },
        {
          id: 'assistant-previous',
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'assistant',
          content: PREVIOUS_ASSISTANT_MESSAGE,
          createdAt: new Date('2026-09-09T00:00:01.000Z'),
        },
        {
          id: 'user-latest',
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'user',
          content: LATEST_USER_MESSAGE,
          createdAt: new Date('2026-09-09T00:00:02.000Z'),
        },
        {
          id: 'assistant-latest',
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'assistant',
          content: LATEST_ASSISTANT_MESSAGE,
          createdAt: new Date('2026-09-09T00:00:03.000Z'),
        },
      ],
    });
  });

  async function renderChatContainer() {
    let result: ReturnType<typeof render> | undefined;
    await act(async () => {
      result = render(
        <App>
          <ChatContainer />
        </App>,
      );
    });
    return result;
  }

  it('deletes the bottom user query and assistant reply from the rendered chat and persistence', async () => {
    await renderChatContainer();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '刪除對話' }));
    });

    await waitFor(() => {
      expect(screen.queryByText(LATEST_USER_MESSAGE)).not.toBeInTheDocument();
      expect(screen.queryByText(LATEST_ASSISTANT_MESSAGE)).not.toBeInTheDocument();
    });
    expect(screen.getByText(PREVIOUS_USER_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText(PREVIOUS_ASSISTANT_MESSAGE)).toBeInTheDocument();
    expect(databaseService.message.deleteManyByConversationId).toHaveBeenCalledWith(
      TEST_CONVERSATION_ID,
      ['user-latest', 'assistant-latest'],
    );
  }, 15000);

  it('shows the delete action only on the bottom assistant reply', async () => {
    await renderChatContainer();

    expect(screen.getAllByRole('button', { name: '刪除對話' })).toHaveLength(1);
  }, 15000);

  it('removes the latest turn from the UI even when persistence deletion fails', async () => {
    vi.mocked(databaseService.message.deleteManyByConversationId).mockRejectedValueOnce(
      new Error('IndexedDB unavailable'),
    );

    await renderChatContainer();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '刪除對話' }));
    });

    await waitFor(() => {
      expect(screen.queryByText(LATEST_USER_MESSAGE)).not.toBeInTheDocument();
      expect(screen.queryByText(LATEST_ASSISTANT_MESSAGE)).not.toBeInTheDocument();
    });
    expect(screen.getByText('已刪除這輪對話')).toBeInTheDocument();
  }, 15000);
});
