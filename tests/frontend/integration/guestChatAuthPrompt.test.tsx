import React from 'react';
import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatContainer } from '@/components/ChatContainer';

const authenticatedFetchMock = vi.hoisted(() => vi.fn());

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
  clearState: vi.fn(),
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
      getUser: vi.fn().mockImplementation(async () => ({ data: { user: currentSession?.user ?? null }, error: null })),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      onAuthStateChange: vi.fn((callback) => {
        authStateCallback = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
    },
  },
}));

vi.mock('@/services/syncService', () => ({
  syncService: {
    pullFromCloud: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: authenticatedFetchMock,
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
  conversationSelectors: {
    activeConversation: (state: typeof conversationState) =>
      state.conversations.find((conversation) => conversation.id === state.activeConversationId),
  },
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
    conversationState.activeConversationId = 'conversation-1';
    conversationState.conversations = [];
    authenticatedFetchMock.mockReset();
    vi.clearAllMocks();
  });

  function renderChat() {
    return render(
      <App>
        <ChatContainer />
      </App>,
    );
  }

  it('opens and closes the mobile sidebar from the floating menu controls', async () => {
    const { container } = renderChat();

    const sidebar = container.querySelector('.areqa-chat-sidebar');
    expect(sidebar).not.toHaveClass('sidebarOpen');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '打開選單' }));
    });
    expect(sidebar).toHaveClass('sidebarOpen');
    expect(container.querySelector('.sidebarOverlay')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(container.querySelector('.sidebarOverlay') as HTMLElement);
    });
    expect(sidebar).not.toHaveClass('sidebarOpen');
    expect(container.querySelector('.sidebarOverlay')).not.toBeInTheDocument();
  });

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

  it('clears rendered history when the session is signed out', async () => {
    renderChat();
    conversationState.conversations = [{ id: 'private-history' } as never];
    chatState.messages = [{ id: 'private-message' } as never];

    await act(async () => {
      authStateCallback?.('SIGNED_OUT', null);
    });

    await waitFor(() => {
      expect(conversationState.clearState).toHaveBeenCalled();
      expect(chatState.clearMessages).toHaveBeenCalled();
      expect(chatState.resetStreamingState).toHaveBeenCalled();
    });
  });

  it('shows the created share URL when clipboard copy fails', async () => {
    const conversationId = 'c35e6795-7de7-4cc6-9854-62c985823523';
    const shareToken = 'share-token-123';
    currentSession = { user: { id: 'user-1' } };
    conversationState.activeConversationId = conversationId;
    conversationState.conversations = [{
      id: conversationId,
      userId: 'user-1',
      title: 'Chain rule',
      createdAt: new Date('2026-08-25T00:00:00Z'),
      updatedAt: new Date('2026-08-25T00:00:00Z'),
      messageCount: 2,
    } as never];
    chatState.messages = [{
      id: '4ef75291-b268-42ca-90d1-7115fcacb845',
      userId: 'user-1',
      conversationId,
      role: 'user',
      content: 'hello',
      createdAt: new Date('2026-08-25T00:00:00Z'),
    } as never];
    authenticatedFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ token: shareToken }),
    });
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('Clipboard denied')) },
      configurable: true,
    });

    renderChat();

    await waitFor(() => expect(screen.getByRole('button', { name: /分享/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /分享/ }));

    expect(await screen.findByText('分享連結已建立：')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: `${window.location.origin}/share/${shareToken}` }))
      .toHaveAttribute('href', `${window.location.origin}/share/${shareToken}`);
    consoleWarn.mockRestore();
  });
});
