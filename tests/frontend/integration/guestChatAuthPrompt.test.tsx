import React from 'react';
import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatContainer } from '@/components/ChatContainer';

const chatState = {
  isStreaming: false,
  error: null,
  messages: [],
  setError: vi.fn(),
  clearMessages: vi.fn(),
  resetStreamingState: vi.fn(),
  setQuotedText: vi.fn(),
};

const conversationState = {
  activeConversationId: 'conversation-1',
  conversations: [],
  clearActiveConversation: vi.fn(),
  setQuotedText: vi.fn(),
};

let authStateCallback: ((event: string, session: unknown) => void) | null = null;
let currentSession: unknown = null;

vi.mock('@/services/chat', () => ({
  sendMessage: vi.fn().mockResolvedValue({ completed: true }),
  initializeChatService: vi.fn().mockResolvedValue(undefined),
  cancelCurrentStream: vi.fn().mockResolvedValue(undefined),
  regenerateMessage: vi.fn().mockResolvedValue(undefined),
  editUserMessage: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockImplementation(async () => ({ data: { session: currentSession } })),
      onAuthStateChange: vi.fn((callback) => {
        authStateCallback = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
    },
  },
}));

vi.mock('@/store/chat', () => ({
  useChatStore: Object.assign(
    (selector: (state: typeof chatState) => unknown) => selector(chatState),
    { getState: () => chatState },
  ),
  chatSelectors: { displayMessages: (state: typeof chatState) => state.messages },
}));

vi.mock('@/store/conversation', () => ({
  useConversationStore: Object.assign(
    (selector: (state: typeof conversationState) => unknown) => selector(conversationState),
    { getState: () => conversationState },
  ),
  conversationSelectors: { activeConversation: () => null },
}));

vi.mock('@/components/ChatContainer/styles', () => ({
  useStyles: () => ({
    cx: (...classes: unknown[]) => classes.filter(Boolean).join(' '),
    styles: new Proxy({}, { get: (_target, property) => String(property) }),
  }),
}));

vi.mock('@/components/ConversationList', () => ({
  ConversationList: () => <div data-testid="conversation-list" />,
}));
vi.mock('@/components/MessageList', () => ({
  MessageList: () => <div data-testid="message-list" />,
}));
vi.mock('@/components/ChatInput', () => ({
  ChatInput: ({ onSend }: { onSend: (content: string) => void }) => (
    <button onClick={() => onSend('訪客問題')}>送出問題</button>
  ),
}));
vi.mock('@/components/TextSelectionToolbar', () => ({ TextSelectionToolbar: () => null }));
vi.mock('@/components/GumPanel', () => ({ GumPanel: () => null }));
vi.mock('@/components/MailboxPanel', () => ({ MailboxPanel: () => null }));
vi.mock('@/components/ProactiveManager', () => ({ ProactiveManager: () => null }));
vi.mock('@/utils/exportChat', () => ({
  exportToMarkdown: vi.fn(),
  exportToDocx: vi.fn(),
  exportToPdf: vi.fn(),
}));

vi.mock('@supabase/auth-ui-react', () => ({ Auth: () => <div data-testid="supabase-auth" /> }));
vi.mock('@supabase/auth-ui-shared', () => ({ ThemeSupa: {} }));

describe('Guest chat authentication prompt flow', () => {
  beforeEach(() => {
    currentSession = null;
    authStateCallback = null;
    chatState.messages = [];
    vi.clearAllMocks();
  });

  function renderChat() {
    return render(
      <App>
        <ChatContainer />
      </App>,
    );
  }

  it('shows the prompt after each completed guest answer until dismissed', async () => {
    renderChat();

    fireEvent.click(screen.getByRole('button', { name: '送出問題' }));
    expect(await screen.findByText('歡迎來到 AREQA')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '維持登出狀態' }));
    await waitFor(() => expect(screen.queryByText('歡迎來到 AREQA')).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: '送出問題' }));
    expect(await screen.findByText('歡迎來到 AREQA')).toBeInTheDocument();
  });

  it('stops showing the prompt after sign-in', async () => {
    renderChat();

    fireEvent.click(screen.getByRole('button', { name: '送出問題' }));
    await screen.findByText('歡迎來到 AREQA');

    await act(async () => {
      authStateCallback?.('SIGNED_IN', { user: { id: 'user-1' } });
    });
    await waitFor(() => expect(screen.queryByText('歡迎來到 AREQA')).not.toBeInTheDocument());

    currentSession = { user: { id: 'user-1' } };
    fireEvent.click(screen.getByRole('button', { name: '送出問題' }));
    await waitFor(() => expect(screen.queryByText('歡迎來到 AREQA')).not.toBeInTheDocument());
  });
});
