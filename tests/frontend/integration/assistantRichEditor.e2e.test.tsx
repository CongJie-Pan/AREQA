import React from 'react';
import { App } from 'antd';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatContainer } from '@/components/ChatContainer';
import { editAssistantMessage } from '@/services/chat';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useNotesStore } from '@/store/notes';

const { TEST_USER_ID, TEST_CONVERSATION_ID, TEST_ASSISTANT_ID } = vi.hoisted(() => ({
  TEST_USER_ID: 'assistant-rich-editor-user',
  TEST_CONVERSATION_ID: 'assistant-rich-editor-conversation',
  TEST_ASSISTANT_ID: 'assistant-rich-editor-message',
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
      updateFeedback: vi.fn().mockResolvedValue(undefined),
    },
    note: {
      clearGuestData: vi.fn().mockResolvedValue(undefined),
      getAll: vi.fn().mockResolvedValue([]),
      addFromMessage: vi.fn().mockResolvedValue(undefined),
    },
  },
}));

vi.mock('@/services/chat', () => ({
  sendMessage: vi.fn().mockResolvedValue({ completed: true }),
  initializeChatService: vi.fn().mockResolvedValue(undefined),
  cancelCurrentStream: vi.fn().mockResolvedValue(undefined),
  regenerateMessage: vi.fn().mockResolvedValue(undefined),
  editUserMessage: vi.fn().mockResolvedValue(undefined),
  editAssistantMessage: vi.fn().mockResolvedValue(undefined),
  deleteLatestConversationTurn: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/services/syncService', () => ({
  syncService: {
    pullFromCloud: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
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
vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn(),
  },
}));

describe('assistant rich editor e2e integration flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNotesStore.setState({ notes: [], loading: false, error: null });
    useConversationStore.setState({
      conversations: [{
        id: TEST_CONVERSATION_ID,
        userId: TEST_USER_ID,
        title: 'Rich editor source chat',
        createdAt: new Date('2026-09-19T00:00:00.000Z'),
        updatedAt: new Date('2026-09-19T00:00:03.000Z'),
        messageCount: 2,
        lastMessagePreview: 'assistant markdown',
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
          id: 'assistant-rich-editor-user-message',
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'user',
          content: 'Please edit the answer.',
          createdAt: new Date('2026-09-19T00:00:01.000Z'),
        },
        {
          id: TEST_ASSISTANT_ID,
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'assistant',
          content: [
            '- parent',
            '  - child',
            '',
            '| A | B |',
            '| --- | --- |',
            '| 1 | 2 |',
          ].join('\n'),
          createdAt: new Date('2026-09-19T00:00:02.000Z'),
        },
      ],
    });
  });

  it('edits an assistant answer as rendered blocks and saves clean Markdown through ChatContainer', async () => {
    render(
      <App>
        <UserPreferencesProvider initialPreferences={{ theme: 'system', language: 'zh-TW' }}>
          <ChatContainer />
        </UserPreferencesProvider>
      </App>,
    );

    await screen.findByText('Please edit the answer.');
    const editButtons = screen.getAllByRole('button', { name: '編輯訊息' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const editor = screen.getByRole('textbox', { name: '編輯訊息' });

    expect(editor).toHaveTextContent('parent');
    expect(editor.querySelector('table')).toBeInTheDocument();
    expect(editor).not.toHaveTextContent('| --- |');

    editor.insertAdjacentHTML('beforeend', '<blockquote><strong>done</strong> <a href="https://example.com/?a=1&amp;b=2">link</a></blockquote>');
    fireEvent.input(editor);
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(editAssistantMessage).toHaveBeenCalledWith(TEST_ASSISTANT_ID, [
        '- parent',
        '  - child',
        '',
        '| A | B |',
        '| --- | --- |',
        '| 1 | 2 |',
        '',
        '> **done** [link](https://example.com/?a=1&b=2)',
      ].join('\n'));
    });
  }, 15000);
});
