import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationList } from '@/components/ConversationList';
import { useConversationStore } from '@/store/conversation';
import { useChatStore } from '@/store/chat';
import type { Conversation } from '@/database/schema';
import { switchConversation } from '@/services/chat';
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
  logConversationHistoryDebugEvent: vi.fn(),
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
        conversationHome: 'AREQA home (New chat)',
        conversationSearch: 'Search chats',
        conversationRecents: 'Recents',
        conversationBranches: 'Conversation branches',
        pinned: 'Pinned',
        today: 'Today',
        yesterday: 'Yesterday',
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

  it('shows a single newest-first list under Recents and lets it collapse', () => {
    useConversationStore.setState({ conversations: [
      conversation({ id: 'older', title: 'Older chat' }),
      conversation({ id: 'newer', title: 'Newer chat', updatedAt: new Date('2026-08-26') }),
    ] });

    const { container } = renderConversationList();
    expect([...container.querySelectorAll('.conv-title')].map((title) => title.textContent))
      .toEqual(['Newer chat', 'Older chat']);
    expect(screen.queryByText('Today')).not.toBeInTheDocument();
    expect(screen.queryByText('Yesterday')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Recents' }));
    expect(screen.queryByText('Older chat')).not.toBeInTheDocument();
  });

  it('returns home through the brand and opens a search result by preview', () => {
    const onNew = vi.fn();
    useConversationStore.setState({ conversations: [
      conversation({ id: 'found', title: 'Stored chat', lastMessagePreview: 'Matching phrase' }),
      conversation({ id: 'other', title: 'Other chat' }),
    ] });

    renderConversationList({ onNew });
    fireEvent.click(screen.getByRole('button', { name: 'AREQA home (New chat)' }));
    expect(onNew).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: 'Search chats' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Search chats' }), { target: { value: 'MATCHING phrase' } });
    expect(screen.queryByRole('button', { name: 'Other chat' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Stored chat' }));
    expect(switchConversation).toHaveBeenCalledWith('found');
  });

  it('keeps Delete last when the conversation has branches', async () => {
    useConversationStore.setState({ conversations: [
      conversation({ id: 'parent', title: 'Parent chat' }),
      conversation({ id: 'child', title: 'Child chat', branchOrigin: {
        conversationId: 'parent', messageId: 'original', copiedMessageId: 'copied', title: 'Parent chat',
      } }),
    ] });

    renderConversationList();
    fireEvent.click(screen.getAllByTitle('Conversation menu')[0]);
    await screen.findByRole('menuitem', { name: /Conversation branches/ });
    expect(screen.getAllByRole('menuitem').at(-1)).toHaveTextContent('Delete');
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

  it('keeps the full title available and toggles the row menu on repeated clicks', async () => {
    const title = 'CULTURECONVERSE跨文化多輪模擬評估框架與實驗結果分析';
    useConversationStore.setState({ conversations: [conversation({ title })] });
    renderConversationList();

    expect(screen.getByTitle(title)).toBeInTheDocument();
    const trigger = screen.getByRole('button', { name: 'Conversation menu' });
    fireEvent.click(trigger);
    await screen.findByRole('menuitem', { name: 'Rename' });
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);
    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('ConversationList workspace switch', () => {
  beforeEach(() => {
    window.localStorage.clear();
    useConversationStore.setState({
      conversations: [
        conversation({ id: 'chat-a', title: 'Chat about cells', lastMessagePreview: 'mitosis' }),
        conversation({ id: 'coach-a', title: 'Topic about feedback', lastMessagePreview: 'mitosis too', kind: 'research_coach' }),
      ],
      activeConversationId: null,
      isLoading: false,
      error: null,
      streamingTitles: {},
      workspace: 'chat',
    });
  });

  it('marks the visible workspace and lists only its conversations', () => {
    const { container } = renderConversationList();
    const titles = () => [...container.querySelectorAll('.conv-title')].map((title) => title.textContent);

    expect(screen.getByRole('button', { name: 'workspaceChatTooltip' })).toHaveAttribute('aria-pressed', 'true');
    expect(titles()).toEqual(['Chat about cells']);

    fireEvent.click(screen.getByRole('button', { name: 'workspaceTopicFinderTooltip' }));

    expect(screen.getByRole('button', { name: 'workspaceTopicFinderTooltip' })).toHaveAttribute('aria-pressed', 'true');
    expect(useConversationStore.getState().workspace).toBe('research_coach');
    expect(titles()).toEqual(['Topic about feedback']);
  });

  it('searches only inside the visible workspace', () => {
    renderConversationList();

    fireEvent.click(screen.getByRole('button', { name: 'Search chats' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Search chats' }), { target: { value: 'mitosis' } });

    const results = document.querySelectorAll('.areqa-conversation-search-result');
    expect([...results].map((result) => result.textContent)).toEqual(['Chat about cells']);
  });

  it('leaves an open conversation of the other workspace and returns home', () => {
    const onNew = vi.fn();
    useConversationStore.setState({ activeConversationId: 'chat-a' });
    renderConversationList({ onNew });

    fireEvent.click(screen.getByRole('button', { name: 'workspaceTopicFinderTooltip' }));

    expect(onNew).toHaveBeenCalledTimes(1);
  });

  it('stays on the home screen when nothing is open', () => {
    const onNew = vi.fn();
    renderConversationList({ onNew });

    fireEvent.click(screen.getByRole('button', { name: 'workspaceTopicFinderTooltip' }));
    fireEvent.click(screen.getByRole('button', { name: 'workspaceTopicFinderTooltip' }));

    expect(onNew).not.toHaveBeenCalled();
    expect(useConversationStore.getState().workspace).toBe('research_coach');
  });
});

describe('ConversationList projects', () => {
  const PROJECT_ID = '7a1c2b6e-1d2a-4c3b-9a8e-123456789abc';
  const at = new Date('2026-11-20T00:00:00.000Z');

  beforeEach(async () => {
    window.localStorage.clear();
    const { useAuthStore } = await import('@/store/auth');
    useAuthStore.setState({ user: { id: 'user-1' } as never });
    const { useProjectStore } = await import('@/store/projects');
    useProjectStore.setState({
      projects: [{
        id: PROJECT_ID, userId: 'user-1', name: 'Diary', instructions: '', useAccountMemory: true, isPinned: true,
        memorySummary: null, memoryDetails: [], memoryUpdatedAt: null, createdAt: at, updatedAt: at,
      }],
      view: { kind: 'list' },
      draftProjectId: null,
    });
    useConversationStore.setState({
      conversations: [
        conversation({ id: 'in-project', title: 'Friendship reflections', projectId: PROJECT_ID }),
        conversation({ id: 'plain', title: 'Loose chat' }),
      ],
      activeConversationId: null,
      isLoading: false,
      streamingTitles: {},
      workspace: 'chat',
    });
  });

  it('nests project chats under a pinned project and opens its page', async () => {
    const onSelectGumPanel = vi.fn();
    renderConversationList({ onSelectGumPanel });

    fireEvent.click(screen.getByText('Diary'));

    const { useProjectStore } = await import('@/store/projects');
    expect(useProjectStore.getState().view).toEqual({ kind: 'project', projectId: PROJECT_ID });
    expect(useProjectStore.getState().draftProjectId).toBe(PROJECT_ID);
    expect(onSelectGumPanel).toHaveBeenCalledWith('projects');
    expect(screen.getAllByText('Friendship reflections').length).toBeGreaterThan(0);
  });

  it('adds a chat to a project from the row menu', async () => {
    vi.mocked(databaseService.conversation.update).mockResolvedValue(undefined);
    renderConversationList();

    fireEvent.click(screen.getAllByTitle('Conversation menu').at(-1)!);
    // "Add to project" is a flyout submenu (image 07): search field, New project, then projects.
    fireEvent.mouseEnter(await screen.findByRole('menuitem', { name: /projectAddTo/ }));
    expect(await screen.findByLabelText('projectSearchOrCreate')).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Diary' }));

    await vi.waitFor(() => expect(databaseService.conversation.update).toHaveBeenCalledWith('plain', { projectId: PROJECT_ID }));
    expect(useConversationStore.getState().conversations.find((item) => item.id === 'plain')?.projectId).toBe(PROJECT_ID);
  });

  it('offers removal only for chats that are in a project', async () => {
    renderConversationList();
    fireEvent.click(screen.getAllByTitle('Conversation menu').at(-1)!);
    fireEvent.mouseEnter(await screen.findByRole('menuitem', { name: /projectAddTo/ }));
    await screen.findByLabelText('projectSearchOrCreate');
    expect(screen.queryByRole('menuitem', { name: /projectRemoveFrom/ })).toBeNull();
  });

  it('creates a project from the submenu search and files the chat into it', async () => {
    vi.mocked(databaseService.conversation.update).mockResolvedValue(undefined);
    const { useProjectStore } = await import('@/store/projects');
    const create = vi.fn().mockResolvedValue({
      id: 'new-project', userId: 'user-1', name: 'Thesis', instructions: '', useAccountMemory: true, isPinned: false,
      memorySummary: null, memoryDetails: [], memoryUpdatedAt: null, createdAt: at, updatedAt: at,
    });
    useProjectStore.setState({ create });
    renderConversationList();

    fireEvent.click(screen.getAllByTitle('Conversation menu').at(-1)!);
    fireEvent.mouseEnter(await screen.findByRole('menuitem', { name: /projectAddTo/ }));
    const search = await screen.findByLabelText('projectSearchOrCreate');
    fireEvent.change(search, { target: { value: 'Thesis' } });
    expect(await screen.findByRole('menuitem', { name: /projectCreateNamed/ })).toBeInTheDocument();
    fireEvent.keyDown(search, { key: 'Enter' });

    await vi.waitFor(() => expect(create).toHaveBeenCalledWith('Thesis'));
    await vi.waitFor(() => expect(databaseService.conversation.update).toHaveBeenCalledWith('plain', { projectId: 'new-project' }));
  });

  it('pinned project rows have their own menu to unpin, rename or delete', async () => {
    const { useProjectStore } = await import('@/store/projects');
    const update = vi.fn().mockResolvedValue(undefined);
    useProjectStore.setState({ update });
    renderConversationList();

    fireEvent.click(screen.getByTitle('projectMenu'));
    fireEvent.click(await screen.findByRole('menuitem', { name: /projectUnpin/ }));
    expect(update).toHaveBeenCalledWith(PROJECT_ID, { isPinned: false });
  });

  it('nested project chats keep the full chat menu', async () => {
    renderConversationList();
    const nested = document.querySelector('[data-project-conversation-id="in-project"]') as HTMLElement;
    expect(nested).toHaveClass('areqa-conversation-project-child');
    fireEvent.click(within(nested).getByTitle('Conversation menu'));
    expect(await screen.findByRole('menuitem', { name: /projectAddTo/ })).toBeInTheDocument();
  });
});
