import 'fake-indexeddb/auto';
import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationList } from '@/components/ConversationList';
import { MessageList } from '@/components/MessageList';
import { ChatInput } from '@/components/ChatInput';
import { HomeWorkspaceSwitch } from '@/components/WorkspaceSwitch';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { db } from '@/database/db';
import { sendMessage } from '@/services/chat';
import { useChatStore } from '@/store/chat';
import { readStoredWorkspace, useConversationStore } from '@/store/conversation/store';
import { resolveConversationKind } from '@/utils/conversationKind';

const USER = 'topic-finder-user';

vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: vi.fn(() => USER),
  getAuthToken: vi.fn(() => 'test-token'),
}));

vi.mock('@/services/syncService', () => ({
  // Cloud sync is out of scope here; every call succeeds without network.
  syncService: new Proxy({}, { get: () => vi.fn().mockResolvedValue(true) }),
  normalizeRequestModes: (value: unknown) => (Array.isArray(value) && value.length ? value : undefined),
}));

vi.mock('@/config/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/api')>();
  return { ...actual, API_CONFIG: { ...actual.API_CONFIG, chatEndpoint: 'http://topic-finder.test/api/v1/stream' } };
});

vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt ?? ''} />,
}));

vi.mock('@/components/Auth', () => ({ UserAuthUI: () => <div /> }));
vi.mock('@/store/mailbox', () => ({ useMailboxStore: () => ({ unreadCount: 0, fetchMails: vi.fn() }) }));
vi.mock('@/services/speech/transcription', () => ({ transcribeSpeech: vi.fn() }));

function sseResponse(answer: string): Response {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(`data: ${JSON.stringify({ choices: [{ delta: { content: answer } }] })}\n\n`));
      controller.enqueue(encoder.encode('data: [DONE]\n\n'));
      controller.close();
    },
  }), { status: 200 });
}

function Harness() {
  const activeId = useConversationStore((state) => state.activeConversationId);
  const isTopicFinder = useConversationStore((state) => resolveConversationKind(state, state.activeConversationId) === 'research_coach');
  return (
    <UserPreferencesProvider>
      <App>
        <ConversationList onNew={() => {
          useConversationStore.getState().clearActiveConversation();
          useChatStore.getState().clearMessages();
        }} />
        <HomeWorkspaceSwitch />
        <MessageList />
        <ChatInput key={activeId ?? 'new'} topicFinder={isTopicFinder} onSend={(text) => sendMessage(text)} />
      </App>
    </UserPreferencesProvider>
  );
}

const streamPayloads = () => vi.mocked(fetch).mock.calls
  .filter(([url]) => String(url).includes('/api/v1/stream'))
  .map(([, init]) => JSON.parse(String((init as RequestInit).body)));

describe('Topic Finder workspace flow', () => {
  beforeEach(async () => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    await db.open();
    await db.conversations.clear();
    await db.messages.clear();
    await db.conversationSyncQueue.clear();
    await db.messageSyncQueue.clear();
    useChatStore.getState().clearMessages();
    useChatStore.setState({ tutorProfile: 'english', searchMode: 'never', useRag: false, useWebSearch: false });
    useConversationStore.setState({ conversations: [], activeConversationId: null, workspace: 'chat', streamingTitles: {} });
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => (
      String(url).includes('/api/v1/stream') ? sseResponse('先說說你的痛點？') : new Response('data: [DONE]\n\n')
    )));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('switches workspace, sends a Topic Finder turn, keeps lists apart, and restores after reload', { timeout: 40_000 }, async () => {
    render(<Harness />);

    // 1. Switch to Topic Finder from the sidebar.
    fireEvent.click(screen.getByRole('button', { name: '選題：找出適合你的研究題目' }));

    // 2. The empty home shows the segmented switch and the Topic Finder copy.
    const segmented = screen.getAllByRole('group', { name: '工作區' });
    expect(segmented).toHaveLength(2);
    expect(screen.getByRole('button', { name: '選題' })).toHaveAttribute('aria-pressed', 'true');

    // 3. The first message creates a research_coach conversation and the request carries its kind.
    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '我做的系統和 Gemini 差不多' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));

    await waitFor(() => expect(streamPayloads()).toHaveLength(1), { timeout: 10_000 });
    const [payload] = streamPayloads();
    expect(payload.conversation_kind).toBe('research_coach');
    expect(payload.tutor_profile).toBe('general');
    await waitFor(() => expect(screen.queryByRole('button', { name: '選題' })).not.toBeInTheDocument(), { timeout: 10_000 });

    const created = useConversationStore.getState().conversations[0];
    expect(created.kind).toBe('research_coach');
    expect((await db.conversations.get(created.id))?.kind).toBe('research_coach');
    const userMessage = useChatStore.getState().messages.find((message) => message.role === 'user');
    expect(userMessage?.requestModes).toBeUndefined();

    // 4. Back in Chat, the Topic Finder conversation is not listed.
    fireEvent.click(screen.getByRole('button', { name: '一般對話' }));
    expect(useConversationStore.getState().activeConversationId).toBeNull();
    expect(document.querySelector(`[data-conversation-id="${created.id}"]`)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '選題：找出適合你的研究題目' }));
    expect(document.querySelector(`[data-conversation-id="${created.id}"]`)).toBeInTheDocument();

    // 5. After a reload, the stored kind and the remembered workspace come back.
    useConversationStore.setState({ conversations: [], activeConversationId: null, workspace: readStoredWorkspace() });
    await useConversationStore.getState().loadConversations(USER);
    expect(useConversationStore.getState().workspace).toBe('research_coach');
    expect(useConversationStore.getState().conversations.find((item) => item.id === created.id)?.kind).toBe('research_coach');
  });

  it('keeps ordinary chat unchanged: English Tutor still applies and no kind is stored', { timeout: 40_000 }, async () => {
    render(<Harness />);

    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: 'Help with Macbeth' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));

    await waitFor(() => expect(streamPayloads()).toHaveLength(1), { timeout: 10_000 });
    expect(streamPayloads()[0]).toMatchObject({ conversation_kind: 'chat', tutor_profile: 'english' });
    const created = useConversationStore.getState().conversations[0];
    expect(created.kind).toBeUndefined();
    expect(useChatStore.getState().messages.find((message) => message.role === 'user')?.requestModes).toEqual(['english_tutor']);
  });
});
