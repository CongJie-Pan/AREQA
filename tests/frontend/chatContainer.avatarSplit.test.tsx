import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatContainer } from '../../frontend/src/components/ChatContainer';

const { chatState, conversationState, liveTutorState } = vi.hoisted(() => ({
  chatState: {
    isStreaming: false,
    error: null,
    messages: [{ id: 'm1', role: 'assistant', content: 'System response', createdAt: new Date() }],
    setError: vi.fn(),
    clearMessages: vi.fn(),
    resetStreamingState: vi.fn(),
    setQuotedText: vi.fn(),
  },
  conversationState: {
    activeConversationId: 'c1',
    isMessageHandoffLoading: false,
    clearState: vi.fn(),
    clearActiveConversation: vi.fn(),
  },
  liveTutorState: {
    isOpen: true,
    isMuted: false,
    avatarEnabled: true,
    open: vi.fn(),
    setMuted: vi.fn(),
    setAvatarEnabled: vi.fn(),
    requestClose: vi.fn(),
  },
}));

vi.mock('antd', () => ({
  App: {
    useApp: () => ({
      message: {
        error: vi.fn(),
        success: vi.fn(),
        loading: vi.fn(() => vi.fn()),
        destroy: vi.fn(),
      },
    }),
  },
  Dropdown: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/components/ConversationList', () => ({
  ConversationList: () => <nav aria-label="Sidebar" />,
}));

vi.mock('@/components/MessageList', () => ({
  MessageList: () => <main>System response</main>,
}));

vi.mock('@/components/ChatInput', () => ({
  ChatInput: () => <form aria-label="Chat input" />,
}));

vi.mock('@/components/TextSelectionToolbar', () => ({
  TextSelectionToolbar: () => null,
}));

vi.mock('@/components/GumPanel', () => ({
  GumPanel: () => null,
}));

vi.mock('@/components/MailboxPanel', () => ({
  MailboxPanel: () => null,
}));

vi.mock('@/components/ProactiveManager', () => ({
  ProactiveManager: () => null,
}));

vi.mock('@/components/Auth', () => ({
  AuthPrompt: () => null,
}));

vi.mock('@/components/LiveTutor', () => ({
  LiveTutorPanel: ({ layout = 'inline' }: { layout?: 'inline' | 'side-pane' }) => (
    <section data-testid="live-tutor-panel" data-layout={layout} />
  ),
}));

vi.mock('@/store/chat', () => ({
  useChatStore: Object.assign(
    (selector: (state: typeof chatState) => unknown) => selector(chatState),
    { getState: () => chatState },
  ),
  chatSelectors: {
    displayMessages: (state: typeof chatState) => state.messages,
  },
}));

vi.mock('@/store/conversation', () => ({
  useConversationStore: Object.assign(
    (selector: (state: typeof conversationState) => unknown) => selector(conversationState),
    { getState: () => conversationState },
  ),
  conversationSelectors: {
    activeConversation: () => null,
  },
}));

vi.mock('@/store/liveTutor', () => ({
  useLiveTutorStore: (selector: (state: typeof liveTutorState) => unknown) => selector(liveTutorState),
}));

vi.mock('@/store/features', () => ({
  useFeatureStore: (selector: (state: { mailbox: boolean; compeer: boolean; fetchFeatures: () => void }) => unknown) =>
    selector({ mailbox: false, compeer: false, fetchFeatures: vi.fn() }),
}));

vi.mock('@/store/auth', () => ({
  initializeAuth: vi.fn(),
  useAuthStore: (selector: (state: { user: null; isInitialized: boolean; validateSession: () => void }) => unknown) =>
    selector({ user: null, isInitialized: true, validateSession: vi.fn() }),
}));

vi.mock('@/services/chat', () => ({
  initializeChatService: vi.fn(),
  sendMessage: vi.fn(),
  cancelCurrentStream: vi.fn(),
  regenerateMessage: vi.fn(),
  editUserMessage: vi.fn(),
}));

vi.mock('@/services/syncService', () => ({
  syncService: {
    pullFromCloud: vi.fn(),
  },
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      clearGuestData: vi.fn(),
    },
    note: {
      clearGuestData: vi.fn(),
      getAll: vi.fn().mockResolvedValue([]),
    },
  },
}));

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({ data: { session: null } })),
    },
  },
}));

vi.mock('@/contexts/UserPreferencesContext', () => ({
  useUserPreferences: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/utils/logger', () => ({
  logger: {
    info: vi.fn(),
    error: vi.fn(),
  },
}));

describe('ChatContainer avatar split layout', () => {
  it('renders the Live Tutor avatar in a resizable side pane when avatar mode is active', () => {
    const { container } = render(<ChatContainer />);

    expect(screen.getByText('System response')).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: 'Resize avatar panel' })).toHaveAttribute(
      'aria-valuenow',
      '320',
    );
    expect(screen.getByLabelText('Live Tutor avatar')).toBeInTheDocument();
    expect(screen.getByTestId('live-tutor-panel')).toHaveAttribute('data-layout', 'side-pane');
    expect(container.querySelector('.areqa-chat-response-pane .areqa-chat-floating-actions')).toBeInTheDocument();
  });

  it('updates the avatar pane width from the separator keyboard control', () => {
    render(<ChatContainer />);

    const separator = screen.getByRole('separator', { name: 'Resize avatar panel' });
    fireEvent.keyDown(separator, { key: 'ArrowLeft' });

    expect(separator).toHaveAttribute('aria-valuenow', '344');
  });
});
