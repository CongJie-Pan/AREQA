import React from 'react';
import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatContainer } from '@/components/ChatContainer';
import { NotesPanel } from '@/components/NotesPanel';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useNotesStore } from '@/store/notes';
import { databaseService } from '@/services/database';
import { switchConversation } from '@/services/chat';
import type { Note } from '@/database/schema';

const {
  TEST_USER_ID,
  TEST_CONVERSATION_ID,
  TEST_ASSISTANT_ID,
  TEST_ASSISTANT_CONTENT,
} = vi.hoisted(() => ({
  TEST_USER_ID: 'notes-user',
  TEST_CONVERSATION_ID: 'notes-conversation',
  TEST_ASSISTANT_ID: 'notes-assistant',
  TEST_ASSISTANT_CONTENT: 'This response should become a saved note with enough detail to require a collapsed preview. '.repeat(8),
}));

let storedNotes: Note[] = [];

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
      getAll: vi.fn(async () => storedNotes),
      addFromMessage: vi.fn(async (message, conversationTitle) => {
        const note = {
          id: 'note-created',
          userId: TEST_USER_ID,
          conversationId: message.conversationId,
          messageId: message.id,
          conversationTitle,
          contentSnapshot: message.content,
          tags: [],
          isPinned: false,
          createdAt: new Date('2026-09-09T00:00:03.000Z'),
          updatedAt: new Date('2026-09-09T00:00:03.000Z'),
        };
        storedNotes = [note];
        return note;
      }),
      updateMetadata: vi.fn(async (id, updates) => {
        const existing = storedNotes.find((note) => note.id === id);
        if (!existing) throw new Error('Note not found');
        const updated = {
          ...existing,
          ...updates,
          updatedAt: new Date('2026-09-09T00:00:04.000Z'),
        };
        storedNotes = storedNotes.map((note) => (note.id === id ? updated : note));
        return updated;
      }),
      updateContentAndSourceMessage: vi.fn(async (id, content) => {
        const existing = storedNotes.find((note) => note.id === id);
        if (!existing) throw new Error('Note not found');
        const updated = {
          ...existing,
          contentSnapshot: content.trim(),
          answerBlocksSnapshot: undefined,
          updatedAt: new Date('2026-09-09T00:00:05.000Z'),
        };
        storedNotes = storedNotes.map((note) => (note.id === id ? updated : note));
        return {
          note: updated,
          sourceMessage: {
            id: TEST_ASSISTANT_ID,
            userId: TEST_USER_ID,
            conversationId: TEST_CONVERSATION_ID,
            role: 'assistant',
            content: content.trim(),
            createdAt: new Date('2026-09-09T00:00:02.000Z'),
          },
        };
      }),
      delete: vi.fn().mockResolvedValue(undefined),
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
  switchConversation: vi.fn().mockResolvedValue(undefined),
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
  ConversationList: ({ onSelectGumPanel }: { onSelectGumPanel: (type: 'notes') => void }) => (
    <button type="button" onClick={() => onSelectGumPanel('notes')}>
      Notes
    </button>
  ),
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

describe('Notes e2e integration flow', () => {
  afterEach(() => {
    window.localStorage.removeItem('areqa:interface-language');
  });
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    storedNotes = [];
    useNotesStore.setState({ notes: [], loading: false, error: null });
    useConversationStore.setState({
      conversations: [{
        id: TEST_CONVERSATION_ID,
        userId: TEST_USER_ID,
        title: 'Notes source chat',
        createdAt: new Date('2026-09-09T00:00:00.000Z'),
        updatedAt: new Date('2026-09-09T00:00:03.000Z'),
        messageCount: 2,
        lastMessagePreview: TEST_ASSISTANT_CONTENT,
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
          id: 'notes-user-message',
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'user',
          content: 'Save the reply.',
          createdAt: new Date('2026-09-09T00:00:01.000Z'),
        },
        {
          id: TEST_ASSISTANT_ID,
          userId: TEST_USER_ID,
          conversationId: TEST_CONVERSATION_ID,
          role: 'assistant',
          content: TEST_ASSISTANT_CONTENT,
          createdAt: new Date('2026-09-09T00:00:02.000Z'),
        },
      ],
    });
  });

  async function saveNote() {
    const source = useChatStore.getState().messages.find((item) => item.id === TEST_ASSISTANT_ID);
    if (!source) throw new Error('Missing assistant message fixture');
    return useNotesStore.getState().addNoteFromMessage(source, 'Notes source chat');
  }

  function renderNotes() {
    return render(<UserPreferencesProvider><App><NotesPanel onClose={vi.fn()} /></App></UserPreferencesProvider>);
  }

  it('updates note cards, source filters, and search when the sidebar conversation title changes', async () => {
    await saveNote();
    renderNotes();
    const sourceFilter = await screen.findByRole('button', { name: /^Notes source chat\s*1$/ });
    fireEvent.click(sourceFilter);

    act(() => {
      useConversationStore.getState().updateConversation(TEST_CONVERSATION_ID, { title: 'Renamed study chat' });
    });

    expect(screen.getByRole('button', { name: /^Renamed study chat\s*1$/ })).toBeInTheDocument();
    expect(within(screen.getByRole('article')).getByText('Renamed study chat')).toBeInTheDocument();
    expect(screen.queryByText('Notes source chat')).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('搜尋筆記'), { target: { value: 'Notes source chat' } });
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('搜尋筆記'), { target: { value: 'Renamed study chat' } });
    expect(screen.getByRole('article')).toBeInTheDocument();
    expect(useNotesStore.getState().notes[0].conversationTitle).toBe('Notes source chat');
  });

  it('uses the latest title when opening previously saved notes after a rename', async () => {
    await saveNote();
    useConversationStore.getState().updateConversation(TEST_CONVERSATION_ID, { title: 'Current conversation title' });
    renderNotes();

    expect(within(await screen.findByRole('article')).getByText('Current conversation title')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Current conversation title\s*1$/ })).toBeInTheDocument();
    expect(screen.queryByText('Notes source chat')).not.toBeInTheDocument();
  });

  it('keeps snapshot titles for unavailable sources and does not use another account’s conversation title', async () => {
    await saveNote();
    useConversationStore.setState({ conversations: [] });
    renderNotes();

    expect(within(await screen.findByRole('article')).getByText('Notes source chat')).toBeInTheDocument();
    const conversation = {
      id: TEST_CONVERSATION_ID, userId: 'other-user', title: 'Other account title',
      createdAt: new Date(), updatedAt: new Date(), messageCount: 0,
    };
    act(() => { useConversationStore.setState({ conversations: [conversation] }); });
    expect(within(screen.getByRole('article')).getByText('Notes source chat')).toBeInTheDocument();
    expect(screen.queryByText('Other account title')).not.toBeInTheDocument();

    act(() => {
      useNotesStore.setState({ notes: [
        { ...storedNotes[0], conversationId: null, conversationTitle: null },
      ] });
    });
    expect(within(screen.getByRole('article')).getByText('未命名對話')).toBeInTheDocument();
  });

  it('saves an assistant response, browses notes from the sidebar, and opens the exact source message', async () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');

    render(
      <UserPreferencesProvider>
        <App>
          <ChatContainer />
        </App>
      </UserPreferencesProvider>,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '加入筆記' }));
    });

    expect(databaseService.note.addFromMessage).toHaveBeenCalledWith(
      expect.objectContaining({ id: TEST_ASSISTANT_ID, content: TEST_ASSISTANT_CONTENT }),
      'Notes source chat',
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Notes' }));
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '筆記' })).toBeInTheDocument();
      expect(document.body).toHaveTextContent('This response should become a saved note');
      expect(screen.getAllByText('This')[0].tagName).toBe('SPAN');
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '展開' }));
    });

    expect(document.body).toHaveTextContent(TEST_ASSISTANT_CONTENT.trim());

    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText('新增標籤'), { target: { value: 'biology' } });
      fireEvent.keyDown(screen.getByPlaceholderText('新增標籤'), { key: 'Enter' });
    });

    await waitFor(() => {
      expect(databaseService.note.updateMetadata).toHaveBeenCalledWith('note-created', { tags: ['biology'] });
      expect(screen.getAllByRole('button', { name: /biology/ }).length).toBeGreaterThanOrEqual(1);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '釘選筆記' }));
    });

    await waitFor(() => {
      expect(databaseService.note.updateMetadata).toHaveBeenCalledWith('note-created', { isPinned: true });
      expect(screen.getByText('釘選筆記')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '編輯訊息' }));
    });

    await act(async () => {
      fireEvent.change(screen.getByRole('textbox', { name: '編輯訊息' }), {
        target: { value: 'Edited note body from notes panel.' },
      });
      fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    });

    await waitFor(() => {
      expect(databaseService.note.updateContentAndSourceMessage).toHaveBeenCalledWith(
        'note-created',
        'Edited note body from notes panel.',
      );
      expect(document.body).toHaveTextContent('Edited note body from notes panel.');
      expect(useChatStore.getState().messages.find((item) => item.id === TEST_ASSISTANT_ID)?.content).toBe(
        'Edited note body from notes panel.',
      );
    });

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: 'biology' })[0]);
    });

    expect(document.body).toHaveTextContent('Edited note body from notes panel.');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '開啟來源位置' }));
    });

    expect(switchConversation).toHaveBeenCalledWith(TEST_CONVERSATION_ID);
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
    });
  }, 30000);
});
