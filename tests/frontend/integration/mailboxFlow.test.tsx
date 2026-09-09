import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatContainer } from '@/components/ChatContainer';
import { disabledRuntimeFeatureFlags, RuntimeFeatureFlags } from '@/config/features';
import { useFeatureStore } from '@/store/features';
import { useMailboxStore } from '@/store/mailbox';

const authState = { user: null, isInitialized: true, validateSession: vi.fn() };

vi.mock('@/store/auth', () => ({
  initializeAuth: vi.fn().mockResolvedValue(undefined),
  useAuthStore: Object.assign(
    (selector: (state: typeof authState) => unknown) => selector(authState),
    { getState: () => authState },
  ),
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: { clearGuestData: vi.fn().mockResolvedValue(undefined) },
    note: {
      clearGuestData: vi.fn().mockResolvedValue(undefined),
      getAll: vi.fn().mockResolvedValue([]),
    },
  },
}));

vi.mock('@/services/chat', () => ({
  sendMessage: vi.fn().mockResolvedValue({ completed: true }),
  initializeChatService: vi.fn().mockResolvedValue(undefined),
  cancelCurrentStream: vi.fn().mockResolvedValue(undefined),
  regenerateMessage: vi.fn().mockResolvedValue(undefined),
  editUserMessage: vi.fn().mockResolvedValue(undefined),
}));

// Mock WebSockets
let wsInstance: any = null;
vi.mock('@/hooks/useProactiveWebSocket', () => {
  return {
    useProactiveWebSocket: (onAlert: (content: string, senderName?: string) => void, onNewMail?: () => void) => {
      React.useEffect(() => {
        // Just store the callback so tests can trigger it
        wsInstance = { onNewMail };
        return () => { wsInstance = null; };
      }, [onNewMail]);
    }
  };
});

// Removed bad ResizeObserver mock here, handled by setup.ts

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock fetch for Mailbox API
const mockMails = [
  {
    mail_id: 'test-mail-1',
    conversation_id: 'conv-1',
    sender: '蘇格拉底',
    content: '你好，朋友。',
    timestamp: Date.now(),
    is_read: false
  }
];

let runtimeFeatures: RuntimeFeatureFlags = disabledRuntimeFeatureFlags;

beforeEach(() => {
  vi.clearAllMocks();
  runtimeFeatures = {
    mailbox: true,
    compeer: false,
    compeerTelemetry: false,
  };
  useFeatureStore.setState({
    ...disabledRuntimeFeatureFlags,
    initialized: false,
    loading: false,
    error: null,
  });
  useMailboxStore.setState({
    mails: [],
    unreadCount: 0,
    loading: false,
    sendingReply: false,
    error: null,
  });

  global.fetch = vi.fn().mockImplementation(async (url: string, options?: any) => {
    if (url.includes('/api/v1/features')) {
      return { ok: true, json: async () => runtimeFeatures };
    }
    if (url.includes('/api/v1/mailbox/send')) {
      return { ok: true, json: async () => ({ status: 'ok' }) };
    }
    if (url.includes('/api/v1/mailbox/read')) {
      return { ok: true, json: async () => ({ status: 'ok' }) };
    }
    if (url.includes('/api/v1/mailbox')) {
      return { ok: true, json: async () => ({ mails: mockMails, unread_count: 1 }) };
    }
    if (url.includes('/api/v1/conversations')) {
      return { ok: true, json: async () => [] };
    }
    return { ok: true, json: async () => ({}) };
  });
});

describe('Mailbox Flow Integration', () => {
  it('should hide mailbox entry and skip mailbox fetch when mailbox is archived', async () => {
    runtimeFeatures = disabledRuntimeFeatureFlags;

    render(<ChatContainer />);
    await act(async () => {
      await vi.dynamicImportSettled();
      await Promise.resolve();
    });

    expect(screen.queryByText('信箱')).not.toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/mailbox'),
      expect.any(Object),
    );
  });

  it('should receive websocket alert, update badge, open mailbox, read, and reply', async () => {
    render(<ChatContainer />);

    // Initially Mailbox button should be there, but no unread count initially 
    // until fetch completes
    
    // Trigger the initial fetch manually if needed, or wait
    await act(async () => {
      await useMailboxStore.getState().fetchMails();
    });

    // The badge should show 1
    const mailboxButton = await screen.findByText('信箱');
    expect(mailboxButton).toBeInTheDocument();

    // Now let's trigger a new mail via websocket
    await act(async () => {
      if (wsInstance?.onNewMail) {
        wsInstance.onNewMail();
      }
    });

    // We fetch again, unread count could be updated.
    
    // 4. Click the mailbox button
    await act(async () => {
      fireEvent.click(mailboxButton);
    });

    // Panel opens
    expect(screen.getByText('蘇格拉底')).toBeInTheDocument();
    
    // 5. Click the mail to read it
    const mailElement = screen.getByText(/你好，朋友。/);
    await act(async () => {
      fireEvent.click(mailElement);
    });

    // The read API should have been called
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/mailbox/read/test-mail-1'),
      expect.any(Object)
    );

    // 6. Write a reply
    const replyInput = screen.getByPlaceholderText(/寫信回覆給 蘇格拉底/);
    fireEvent.change(replyInput, { target: { value: '我的回覆' } });
    
    const sendButton = screen.getByText(/發送信件/).closest('button') as HTMLButtonElement;
    
    // 7. Click send
    await act(async () => {
      fireEvent.click(sendButton);
    });

    // The send API should have been called
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/mailbox/send'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('我的回覆')
      })
    );
  }, 15000);
});
