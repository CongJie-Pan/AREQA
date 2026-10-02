import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatContainer } from '../../frontend/src/components/ChatContainer';
import { cancelConversationImage, generateConversationImage } from '@/services/generatedImages';
import { cancelCurrentStream, initializeChatService } from '@/services/chat';
import { syncService } from '@/services/syncService';

const authState = vi.hoisted(() => ({ user: null as { id: string } | null }));
vi.mock('@/services/generatedImages', () => ({
  generateConversationImage: vi.fn(async () => ({ completed: true })),
  cancelConversationImage: vi.fn(() => true),
}));

const { chatState, conversationState, liveTutorState } = vi.hoisted(() => ({
  chatState: {
    isStreaming: false,
    imageGenerationRequests: {} as Record<string, { userId: string; conversationId: string | null; assistantMessageId: string | null }>,
    error: null,
    messages: [{ id: 'm1', role: 'assistant', content: 'System response', createdAt: new Date() }],
    setError: vi.fn(),
    clearMessages: vi.fn(),
    resetStreamingState: vi.fn(),
    setQuotedText: vi.fn(),
  },
  conversationState: {
    activeConversationId: 'c1' as string | null,
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
  ConversationList: ({ onToggleSidebar }: { onToggleSidebar: () => void }) => (
    <nav aria-label="Sidebar"><button onClick={onToggleSidebar}>Close sidebar</button></nav>
  ),
}));

vi.mock('@/components/MessageList', () => ({
  MessageList: () => <main>System response</main>,
}));

vi.mock('@/components/MessageList/ImageGenerationLoading', () => ({
  ImageGenerationLoading: ({ caption }: { caption: string }) => <div role="status">{caption}</div>,
}));

vi.mock('@/components/ChatInput', () => ({
  ChatInput: ({ onSend, isGeneratingImage, disabled, onStop }: {
    onSend: (content: string, attachments: File[], options: { createImage: boolean }) => unknown;
    isGeneratingImage: boolean;
    disabled: boolean;
    onStop: () => void;
  }) => <form aria-label="Chat input" data-image-busy={isGeneratingImage} data-disabled={disabled}>
    {isGeneratingImage && <button type="button" onClick={onStop}>Stop image</button>}
    <button type="button" onClick={() => {
      void onSend('根據附件產圖', [new File(['source'], 'source.txt')], { createImage: true });
    }}>Create attachment image</button>
  </form>,
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
  useAuthStore: (selector: (state: { user: { id: string } | null; isInitialized: boolean; validateSession: () => void }) => unknown) =>
    selector({ user: authState.user, isInitialized: true, validateSession: vi.fn() }),
}));

vi.mock('@/services/chat', () => ({
  initializeChatService: vi.fn(async () => {}),
  sendMessage: vi.fn(),
  cancelCurrentStream: vi.fn(),
  regenerateMessage: vi.fn(),
  editUserMessage: vi.fn(),
}));

vi.mock('@/services/syncService', () => ({
  syncService: {
    pullFromCloud: vi.fn(async () => {}),
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
    language: 'zh-TW',
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
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = null;
    chatState.imageGenerationRequests = {};
    conversationState.activeConversationId = 'c1';
  });

  it('does not reload history when the same account receives a new session user object', async () => {
    authState.user = { id: 'user-a' };
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<ChatContainer />); });
    expect(initializeChatService).toHaveBeenCalledTimes(2);
    expect(syncService.pullFromCloud).toHaveBeenCalledTimes(1);

    authState.user = { id: 'user-a' };
    await act(async () => { view.rerender(<ChatContainer />); });
    expect(initializeChatService).toHaveBeenCalledTimes(2);
    expect(syncService.pullFromCloud).toHaveBeenCalledTimes(1);
    expect(conversationState.clearState).not.toHaveBeenCalled();
  });

  it('clears old history on account changes and logout while still loading the new account', async () => {
    authState.user = { id: 'user-a' };
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<ChatContainer />); });
    vi.clearAllMocks();

    authState.user = { id: 'user-b' };
    await act(async () => { view.rerender(<ChatContainer />); });
    expect(conversationState.clearState).toHaveBeenCalledTimes(1);
    expect(chatState.clearMessages).toHaveBeenCalledTimes(1);
    expect(initializeChatService).toHaveBeenCalledTimes(2);
    expect(initializeChatService).toHaveBeenCalledWith('user-b');
    expect(syncService.pullFromCloud).toHaveBeenCalledWith('user-b');
    vi.clearAllMocks();

    authState.user = null;
    await act(async () => { view.rerender(<ChatContainer />); });
    expect(conversationState.clearState).toHaveBeenCalledTimes(1);
    expect(chatState.clearMessages).toHaveBeenCalledTimes(1);
    expect(initializeChatService).not.toHaveBeenCalled();
    expect(syncService.pullFromCloud).not.toHaveBeenCalled();
  });

  it('does not start cloud synchronization for an account whose initial load finishes after logout', async () => {
    let finish!: () => void;
    vi.mocked(initializeChatService).mockReturnValueOnce(new Promise<void>((resolve) => { finish = resolve; }));
    authState.user = { id: 'user-a' };
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<ChatContainer />); });
    authState.user = null;
    await act(async () => { view.rerender(<ChatContainer />); });
    await act(async () => { finish(); });
    expect(syncService.pullFromCloud).not.toHaveBeenCalled();
    expect(initializeChatService).toHaveBeenCalledTimes(1);
  });

  it('connects selected image job state and Stop without cancelling the voice/text stream', async () => {
    authState.user = { id: 'user-a' };
    chatState.imageGenerationRequests = {
      request: { userId: 'user-a', conversationId: 'c1', assistantMessageId: 'image-message' },
    };
    await act(async () => { render(<ChatContainer />); });
    expect(screen.getByRole('form', { name: 'Chat input' })).toHaveAttribute('data-image-busy', 'true');
    expect(screen.getByRole('form', { name: 'Chat input' })).toHaveAttribute('data-disabled', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Stop image' }));
    await waitFor(() => expect(cancelConversationImage).toHaveBeenCalledWith('c1'));
    expect(cancelCurrentStream).not.toHaveBeenCalled();
  });

  it('does not show Stop for another conversation or account', async () => {
    authState.user = { id: 'user-a' };
    chatState.imageGenerationRequests = {
      otherConversation: { userId: 'user-a', conversationId: 'c2', assistantMessageId: 'image-a' },
      otherAccount: { userId: 'user-b', conversationId: 'c1', assistantMessageId: 'image-b' },
    };
    await act(async () => { render(<ChatContainer />); });
    expect(screen.getByRole('form', { name: 'Chat input' })).toHaveAttribute('data-image-busy', 'false');
    expect(screen.queryByRole('button', { name: 'Stop image' })).not.toBeInTheDocument();
  });

  it('does not cancel voice/text if an image completes just before Stop is clicked', async () => {
    authState.user = { id: 'user-a' };
    chatState.imageGenerationRequests = {
      request: { userId: 'user-a', conversationId: 'c1', assistantMessageId: 'image-message' },
    };
    vi.mocked(cancelConversationImage).mockReturnValueOnce(false);
    await act(async () => { render(<ChatContainer />); });
    fireEvent.click(screen.getByRole('button', { name: 'Stop image' }));
    expect(cancelCurrentStream).not.toHaveBeenCalled();
  });

  it('shows a preparation card before a new conversation and assistant message exist', async () => {
    authState.user = { id: 'user-a' };
    conversationState.activeConversationId = null;
    chatState.imageGenerationRequests = {
      request: { userId: 'user-a', conversationId: null, assistantMessageId: null },
    };
    await act(async () => { render(<ChatContainer />); });
    expect(screen.getByRole('status')).toHaveTextContent('正在準備圖片…');
    expect(screen.getByRole('button', { name: 'Stop image' })).toBeInTheDocument();
  });

  it('forwards attachments from Create Image to the image workflow', async () => {
    authState.user = { id: 'user-a' };
    await act(async () => { render(<ChatContainer />); });
    fireEvent.click(screen.getByRole('button', { name: 'Create attachment image' }));
    await waitFor(() => expect(generateConversationImage).toHaveBeenCalledWith(
      '根據附件產圖', 'c1', expect.any(String), true, { attachments: [expect.any(File)] },
    ));
  });
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

  it('wires sidebar resizing into the layout and preserves its width across toggles', () => {
    const { container } = render(<ChatContainer />);
    const separator = screen.getByRole('separator', { name: 'resizeSidebar' });
    fireEvent.keyDown(separator, { key: 'ArrowRight' });
    expect(separator).toHaveAttribute('aria-valuenow', '296');
    expect((container.querySelector('.areqa-chat-sidebar') as HTMLElement).style
      .getPropertyValue('--areqa-sidebar-width')).toBe('296px');
    fireEvent.click(screen.getByRole('button', { name: 'Close sidebar' }));
    expect(screen.queryByRole('separator', { name: 'resizeSidebar' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('openSidebar'));
    expect(screen.getByRole('separator', { name: 'resizeSidebar' })).toHaveAttribute('aria-valuenow', '296');
  });
});
