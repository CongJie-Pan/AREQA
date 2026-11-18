import 'fake-indexeddb/auto';
import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationList } from '@/components/ConversationList';
import { TopicCardPanel } from '@/components/TopicCard';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { db } from '@/database/db';
import type { Conversation, Message } from '@/database/schema';
import { useTopicCard } from '@/hooks/useTopicCard';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation/store';
import { exploreCandidateInBranch } from '@/services/topicFinderBranch';

const USER = 'divergence-user';
const MAIN = '7c2d9e10-4f3a-4b2c-9d1e-0a1b2c3d4e5f';

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
  return { ...actual, API_CONFIG: { ...actual.API_CONFIG, chatEndpoint: 'http://divergence.test/api/v1/stream' } };
});
vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt ?? ''} />,
}));
vi.mock('@/components/Auth', () => ({ UserAuthUI: () => <div /> }));
vi.mock('@/store/mailbox', () => ({ useMailboxStore: () => ({ unreadCount: 0, fetchMails: vi.fn() }) }));

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };
const mainCard = {
  stage: 2, version: 2, pending: null,
  card: {
    ...empty, pain_point: '系統和 Gemini 差不多', candidates: ['回覆策略與反思', '提問與講解的平衡'],
    discarded: [{ topic: '記憶機制', filter: 1, reason: '技術會自動解決', can_return: true }],
  },
  history: [{ version: 1, stage: 1, note: '加入痛點', confirmed_at: 1 }, { version: 2, stage: 2, note: '淘汰記憶機制', confirmed_at: 2 }],
};

function sse(answer: string): Response {
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
  const topicCard = useTopicCard(MAIN, true);
  return (
    <UserPreferencesProvider>
      <App>
        <ConversationList onNew={() => useConversationStore.getState().clearActiveConversation()} />
        <TopicCardPanel
          topicCard={topicCard}
          onExploreCandidate={(candidate) => {
            void exploreCandidateInBranch({
              sourceConversationId: MAIN, title: `候選 · ${candidate}`, firstMessage: `我想在這條分支深入探索這個候選題目：「${candidate}」`,
            });
          }}
        />
      </App>
    </UserPreferencesProvider>
  );
}

const streamBodies = () => vi.mocked(fetch).mock.calls
  .filter(([url]) => String(url).includes('/api/v1/stream'))
  .map(([, init]) => JSON.parse(String((init as RequestInit).body)));

describe('Topic Finder divergence', () => {
  beforeEach(async () => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    await db.open();
    await db.conversations.clear();
    await db.messages.clear();
    const now = Date.now();
    const main: Conversation = {
      id: MAIN, userId: USER, title: '主線選題', createdAt: new Date(now - 10_000), updatedAt: new Date(now - 10_000),
      messageCount: 2, lastMessagePreview: '', kind: 'research_coach',
    };
    const history: Message[] = [
      { id: '0e1f2a3b-4c5d-4e6f-8a7b-9c0d1e2f3a4b', userId: USER, conversationId: MAIN, role: 'user', content: '我的痛點', createdAt: new Date(now - 9_000) },
      { id: '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d', userId: USER, conversationId: MAIN, role: 'assistant', content: '這裡有兩個候選題目', createdAt: new Date(now - 8_000) },
    ];
    await db.conversations.add(main);
    await db.messages.bulkAdd(history);
    useChatStore.getState().clearMessages();
    useChatStore.setState({
      messages: history.map((message) => ({ ...message, isStreaming: false })) as never,
      isStreaming: false, tutorProfile: 'english', searchMode: 'never', useRag: false, useWebSearch: false,
    });
    useConversationStore.setState({ conversations: [main], activeConversationId: MAIN, workspace: 'research_coach', streamingTitles: {} });
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      const target = String(url);
      if (target.includes('/api/v1/stream')) return sse('我們來看看這個候選。');
      if (target.includes(`/research-coach/${MAIN}/card`)) return new Response(JSON.stringify(mainCard));
      return new Response('data: [DONE]\n\n');
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it('branches each candidate inside Topic Finder and leaves the main card untouched', { timeout: 40_000 }, async () => {
    render(<Harness />);
    await screen.findByText('提問與講解的平衡');

    for (const candidate of ['回覆策略與反思', '提問與講解的平衡']) {
      // Each branch is cut from the main conversation's latest finished reply.
      useConversationStore.setState({ activeConversationId: MAIN });
      fireEvent.click(screen.getByRole('button', { name: `開分支探索：${candidate}` }));
      await waitFor(() => expect(streamBodies().some((body) => body.messages.at(-1).content.includes(candidate))).toBe(true), { timeout: 10_000 });
      await waitFor(() => expect(useChatStore.getState().isStreaming).toBe(false), { timeout: 10_000 });
      useChatStore.setState({
        messages: (await db.messages.where('conversationId').equals(MAIN).toArray()).map((message) => ({ ...message, isStreaming: false })) as never,
      });
    }

    const branches = useConversationStore.getState().conversations.filter((item) => item.branchOrigin?.conversationId === MAIN);
    expect(branches).toHaveLength(2);
    expect(branches.every((item) => item.kind === 'research_coach')).toBe(true);
    for (const branch of branches) expect((await db.conversations.get(branch.id))?.kind).toBe('research_coach');

    const bodies = streamBodies();
    expect(bodies).toHaveLength(2);
    expect(bodies.every((body) => body.conversation_kind === 'research_coach' && body.isolated_context === true)).toBe(true);
    expect(new Set(bodies.map((body) => body.conversation_id))).toEqual(new Set(branches.map((item) => item.id)));
    expect(bodies.every((body) => body.tutor_profile === 'general')).toBe(true);

    // The main conversation is never written to, and no card request targets a branch.
    expect(await db.messages.where('conversationId').equals(MAIN).count()).toBe(2);
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/confirm'))).toBe(false);

    // Branches are listed in Topic Finder only.
    useConversationStore.getState().setWorkspace('research_coach');
    await waitFor(() => branches.forEach((item) => expect(document.querySelector(`[data-conversation-id="${item.id}"]`)).toBeInTheDocument()));
    useConversationStore.getState().clearActiveConversation();
    useConversationStore.getState().setWorkspace('chat');
    await waitFor(() => branches.forEach((item) => expect(document.querySelector(`[data-conversation-id="${item.id}"]`)).not.toBeInTheDocument()));
  });

  it('exports the main card with discarded topics and version history', { timeout: 20_000 }, async () => {
    const createObjectURL = vi.fn(() => 'blob:card');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<Harness />);
    await screen.findByText('提問與講解的平衡');

    fireEvent.click(screen.getByRole('button', { name: '匯出 Markdown' }));

    const blob = (createObjectURL.mock.calls[0] as unknown as [Blob])[0];
    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(blob);
    });
    expect(text).toContain('記憶機制 (第 1 階段淘汰)');
    expect(text).toContain('v2 · 第 2 階段: 淘汰記憶機制');
    click.mockRestore();
  });
});
