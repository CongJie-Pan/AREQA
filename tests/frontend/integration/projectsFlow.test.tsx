import 'fake-indexeddb/auto';
import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationList } from '@/components/ConversationList';
import { MessageList } from '@/components/MessageList';
import { ChatInput } from '@/components/ChatInput';
import { ProjectsPanel } from '@/components/Projects';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { db } from '@/database/db';
import { sendMessage, switchConversation } from '@/services/chat';
import { useAuthStore } from '@/store/auth';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation/store';
import { useProjectStore } from '@/store/projects';

/**
 * Projects flow over real stores, IndexedDB, chat service and stream client.
 * Only the network is faked: Supabase (projects table), the chat stream, and
 * the project-memory API.
 */

const USER = 'projects-flow-user';

const cloud = vi.hoisted(() => ({ upserts: [] as Array<Record<string, unknown>> }));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: () => ({
      upsert: async (row: Record<string, unknown>) => { cloud.upserts.push(row); return { error: null }; },
      select: () => ({ eq: async () => ({ data: [], error: null }) }),
      delete: () => ({ eq: async () => ({ error: null }) }),
    }),
    auth: { refreshSession: async () => ({ data: { session: null }, error: null }) },
  },
}));

vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: vi.fn(() => USER),
  getAuthToken: vi.fn(() => 'test-token'),
}));

vi.mock('@/services/syncService', () => ({
  syncService: new Proxy({}, { get: () => vi.fn().mockResolvedValue(true) }),
  normalizeRequestModes: (value: unknown) => (Array.isArray(value) && value.length ? value : undefined),
}));

vi.mock('@/config/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/api')>();
  return { ...actual, API_CONFIG: { ...actual.API_CONFIG, chatEndpoint: 'http://projects.test/api/v1/stream' } };
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

/** Mirrors ChatContainer's panel routing: the Projects page replaces the chat view. */
function Harness() {
  const [panel, setPanel] = React.useState<'projects' | null>(null);
  const activeId = useConversationStore((state) => state.activeConversationId);
  const leaveConversation = () => {
    useConversationStore.getState().clearActiveConversation();
    useChatStore.getState().clearMessages();
  };
  return (
    <UserPreferencesProvider>
      <App>
        <ConversationList
          onNew={() => { useProjectStore.getState().setDraftProjectId(null); leaveConversation(); setPanel(null); }}
          onSelect={() => { useProjectStore.getState().setDraftProjectId(null); setPanel(null); }}
          onSelectGumPanel={(type) => {
            if (type !== 'projects') return;
            const view = useProjectStore.getState().view;
            useProjectStore.getState().setDraftProjectId(view.kind === 'project' ? view.projectId : null);
            leaveConversation();
            setPanel('projects');
          }}
        />
        {panel === 'projects' ? (
          <ProjectsPanel
            onStartChat={(text, attachments) => { setPanel(null); return sendMessage(text, undefined, attachments); }}
            onOpenConversation={(id) => { void switchConversation(id).then(() => setPanel(null)); }}
            onOpenAccountMemory={() => setPanel(null)}
          />
        ) : (
          <>
            <MessageList />
            <ChatInput key={activeId ?? 'new'} onSend={(text) => sendMessage(text)} />
          </>
        )}
      </App>
    </UserPreferencesProvider>
  );
}

const streamPayloads = () => vi.mocked(fetch).mock.calls
  .filter(([url]) => String(url).includes('/api/v1/stream'))
  .map(([, init]) => JSON.parse(String((init as RequestInit).body)));

async function sendFromComposer(text: string) {
  fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: text } });
  fireEvent.click(screen.getByLabelText('發送訊息'));
}

async function waitForStreams(count: number) {
  await waitFor(() => expect(streamPayloads()).toHaveLength(count), { timeout: 10_000 });
  await waitFor(() => expect(useChatStore.getState().isStreaming).toBe(false), { timeout: 10_000 });
}

describe('Projects flow', () => {
  beforeEach(async () => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    cloud.upserts = [];
    await db.open();
    await Promise.all([
      db.conversations.clear(), db.messages.clear(), db.projects.clear(),
      db.conversationSyncQueue.clear(), db.messageSyncQueue.clear(),
    ]);
    useAuthStore.setState({ user: { id: USER } as never });
    useProjectStore.getState().reset();
    useChatStore.getState().clearMessages();
    useChatStore.setState({ searchMode: 'never', useRag: false, useWebSearch: false });
    useConversationStore.setState({ conversations: [], activeConversationId: null, workspace: 'chat', streamingTitles: {} });
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      const target = String(url);
      if (target.includes('/api/v1/stream')) return sseResponse('收到');
      if (target.includes('/memory/refresh')) {
        return new Response(JSON.stringify({
          refreshed: true,
          memory: { summary: '碩一學生，每晚寫日記', details: ['住在台北宿舍'], updated_at: '2026-11-25T08:00:00Z' },
        }), { status: 200 });
      }
      return new Response('data: [DONE]\n\n');
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('creates a project, chats inside it with project_id, keeps new chats outside, and links chats later', { timeout: 60_000 }, async () => {
    render(<Harness />);

    // 1. Sidebar → Projects → create "Diary"; the new project's page opens.
    fireEvent.click(screen.getByRole('button', { name: '專案' }));
    expect(await screen.findByRole('heading', { name: '專案' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新增專案' }));
    fireEvent.change(await screen.findByLabelText('專案名稱'), { target: { value: 'Diary' } });
    fireEvent.click(screen.getByRole('button', { name: /儲\s*存/ }));
    expect(await screen.findByRole('heading', { name: 'Diary' })).toBeInTheDocument();
    const project = useProjectStore.getState().projects[0];
    await waitFor(() => expect(cloud.upserts.some((row) => row.id === project.id && row.name === 'Diary')).toBe(true));

    // 2. Instructions are saved locally and pushed to Supabase.
    const side = screen.getByText('指示').closest('aside') as HTMLElement;
    fireEvent.click(within(side).getByRole('button', { name: '新增' }));
    const dialog = await screen.findByRole('dialog', { name: '指示' });
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: '先給重點' } });
    fireEvent.click(screen.getAllByRole('button', { name: /儲\s*存/ }).at(-1)!);
    await waitFor(() => expect((useProjectStore.getState().projects[0]).instructions).toBe('先給重點'));
    await waitFor(() => expect(cloud.upserts.at(-1)).toMatchObject({ id: project.id, instructions: '先給重點' }));

    // 3. The project composer starts a conversation that belongs to the project.
    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '今天好累' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));
    await waitForStreams(1);
    expect(streamPayloads()[0].project_id).toBe(project.id);
    const projectChatId = useConversationStore.getState().activeConversationId!;
    expect((await db.conversations.get(projectChatId))?.projectId).toBe(project.id);

    // 4. Follow-up turns in that conversation keep sending project_id.
    await sendFromComposer('再多說一點');
    await waitForStreams(2);
    expect(streamPayloads()[1].project_id).toBe(project.id);

    // 5. "New chat" afterwards is an ordinary chat.
    fireEvent.click(screen.getByRole('button', { name: '新對話' }));
    await sendFromComposer('一般問題');
    await waitForStreams(3);
    expect(streamPayloads()[2]).not.toHaveProperty('project_id');
    const plainChatId = useConversationStore.getState().activeConversationId!;
    expect((await db.conversations.get(plainChatId))?.projectId).toBeUndefined();

    // 6. "Add to project" links the plain chat; its next turn carries the project.
    const plainRow = document.querySelector(`[data-conversation-id="${plainChatId}"]`) as HTMLElement;
    fireEvent.click(within(plainRow).getByTitle('對話選單'));
    fireEvent.click(await screen.findByRole('menuitem', { name: /加入專案/ }));
    fireEvent.click(await screen.findByRole('option', { name: 'Diary' }));
    await waitFor(async () => expect((await db.conversations.get(plainChatId))?.projectId).toBe(project.id));
    await sendFromComposer('接著問');
    await waitForStreams(4);
    expect(streamPayloads()[3].project_id).toBe(project.id);

    // 7. The project page lists both chats; opening Memory refreshes the stale profile.
    fireEvent.click(screen.getByRole('button', { name: '專案' }));
    fireEvent.click(await screen.findByText('Diary'));
    await waitFor(() => expect(screen.getAllByRole('button').filter((button) => (
      button.className.includes('conversationRow'))).length).toBe(2));
    fireEvent.click(within(screen.getByText('記憶').closest('aside') as HTMLElement).getByRole('button', { name: '檢視' }));
    expect(await screen.findByText('碩一學生，每晚寫日記')).toBeInTheDocument();
    const refreshCalls = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes('/memory/refresh'));
    expect(refreshCalls).toHaveLength(1);
    expect(String(refreshCalls[0][0])).toBe(`/api/projects/${project.id}/memory/refresh`);
    expect((await db.projects.get(project.id))?.memoryDetails).toEqual(['住在台北宿舍']);
  });
});
