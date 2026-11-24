import 'fake-indexeddb/auto';
import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatInput } from '@/components/ChatInput';
import { TopicCardPanel } from '@/components/TopicCard';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { db } from '@/database/db';
import { useTopicCard } from '@/hooks/useTopicCard';
import { sendMessage } from '@/services/chat';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation/store';

const USER = 'topic-card-user';
const CONVERSATION = '6a1f0d3e-2b4c-4d5e-8f60-718293a4b5c6';

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
  return { ...actual, API_CONFIG: { ...actual.API_CONFIG, chatEndpoint: 'http://topic-card.test/api/v1/stream' } };
});
vi.mock('@/services/speech/transcription', () => ({ transcribeSpeech: vi.fn() }));
// Keep the post-answer refresh quick in tests.
vi.mock('@/hooks/useTopicCard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useTopicCard')>();
  actual.TOPIC_CARD_REFRESH_DELAYS_MS.splice(0, actual.TOPIC_CARD_REFRESH_DELAYS_MS.length, 50);
  return actual;
});

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };
let cardResponse: () => Response;
let confirmResponse: () => Response;
let focusResponse: () => Response;
let rejectResponse: () => Response;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

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
  const topicCard = useTopicCard(CONVERSATION, true);
  return (
    <UserPreferencesProvider>
      <App>
        <TopicCardPanel topicCard={topicCard} />
        <ChatInput topicFinder onSend={(text) => sendMessage(text, CONVERSATION)} />
      </App>
    </UserPreferencesProvider>
  );
}

const calls = (part: string) => vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes(part));

describe('Topic Finder topic card flow', () => {
  beforeEach(async () => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    await db.open();
    await db.conversations.clear();
    await db.messages.clear();
    const now = new Date();
    const conversation = {
      id: CONVERSATION, userId: USER, title: '選題', createdAt: now, updatedAt: now,
      messageCount: 0, lastMessagePreview: '', kind: 'research_coach' as const,
    };
    await db.conversations.add(conversation);
    useChatStore.getState().clearMessages();
    useChatStore.setState({ tutorProfile: 'general', searchMode: 'never', useRag: false, useWebSearch: false, isStreaming: false });
    useConversationStore.setState({ conversations: [conversation], activeConversationId: CONVERSATION, workspace: 'research_coach' });
    cardResponse = () => json({ stage: 1, version: 0, card: empty, pending: null, history: [] });
    confirmResponse = () => json({ adopted: true, state: {
      stage: 1, version: 1, card: { ...empty, pain_point: '系統和 Gemini 差不多' }, pending: null,
      history: [{ version: 1, stage: 1, note: '加入痛點', confirmed_at: 1 }],
    } });
    focusResponse = () => json({ error: 'Topic card unavailable' }, 503);
    rejectResponse = () => json({ error: 'Topic card unavailable' }, 503);
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      const target = String(url);
      if (target.includes('/focus')) return focusResponse();
      if (target.includes('/reject')) return rejectResponse();
      if (target.includes('/api/v1/stream')) return sse('先說說你的痛點？');
      if (target.includes('/card')) return cardResponse();
      if (target.includes('/confirm')) return confirmResponse();
      if (target.includes('/stage')) return json({ stage: 2, version: 1, card: { ...empty, pain_point: '系統和 Gemini 差不多' }, pending: null, history: [] });
      return new Response('data: [DONE]\n\n');
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it('shows a proposal after an answer, adopts it on request, and moves stage only when the learner asks', { timeout: 40_000 }, async () => {
    render(<Harness />);
    expect(await screen.findByText('還沒有確認的內容；採用上面的草稿後，會出現在這裡。')).toBeInTheDocument();

    // The backend proposes a draft after the answer; the card stays at stage 1.
    cardResponse = () => json({ stage: 1, version: 0, card: empty, pending: {
      card: { ...empty, pain_point: '系統和 Gemini 差不多' }, notes: ['加入痛點'],
    }, history: [] });
    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '我做的系統和 Gemini 差不多' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));

    await waitFor(() => expect(calls('/api/v1/stream')).toHaveLength(1), { timeout: 10_000 });
    expect(await screen.findByRole('group', { name: /要更新到下方「目前的題目」嗎/ }, { timeout: 10_000 })).toHaveTextContent('系統和 Gemini 差不多');
    // The draft does not move the learner: they are still at stage 1.
    expect(screen.getByText('第 1 階段')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '需要' }));

    await waitFor(() => expect(screen.getByText('版本 v1')).toBeInTheDocument());
    expect(screen.getByText('第 1 階段')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: /目前的題目/ })).not.toBeInTheDocument();
    expect(JSON.parse(String(calls('/confirm')[0][1]?.body))).toEqual({ version: 0 });
    expect(calls('/stage')).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: '下一階段 →' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '有沒有很簡單的解法？' })).toBeInTheDocument());
    expect(JSON.parse(String(calls('/stage')[0][1]?.body))).toEqual({ stage: 2 });
  });

  it('lets the learner set the coach focus aside, then shows the check-back after a revision', { timeout: 40_000 }, async () => {
    const measures = [{ term: '篩選能力', measure: '' }, { term: '使用頻率', measure: '' }];
    const card = { ...empty, mother_question: '工具代勞會不會削弱篩選能力', operationalization: measures };
    const first = { id: 'measure:aaaaaaaaaaaa', kind: 'measure', term: '篩選能力' };
    const second = { id: 'measure:bbbbbbbbbbbb', kind: 'measure', term: '使用頻率' };
    cardResponse = () => json({ stage: 4, version: 2, card, pending: null, history: [], focus: first });
    focusResponse = () => json({ stage: 4, version: 2, card, pending: null, history: [], skipped_focus: [first.id], focus: second });
    render(<Harness />);

    expect(await screen.findByText('這輪先看：「篩選能力」要用什麼證據看出來')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '換一個' }));
    expect(await screen.findByText('這輪先看：「使用頻率」要用什麼證據看出來')).toBeInTheDocument();
    expect(JSON.parse(String(calls('/focus')[0][1]?.body))).toEqual({ gap_id: first.id });

    // The learner revises the mother question; the coach will check stage 4 next turn.
    const revised = { ...card, mother_question: '人還會發展自己的篩選能力嗎' };
    cardResponse = () => json({ stage: 3, version: 2, card, pending: { card: revised, notes: ['母問題往上抽一層'] }, history: [] });
    confirmResponse = () => json({ adopted: true, state: {
      stage: 3, version: 3, card: revised, pending: null, history: [],
      review: { version: 3, changed: ['mother_question'], stages: [4], created_at: 1 }, focus: null,
    } });
    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '我想把問題往上抽一層' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));
    fireEvent.click(await screen.findByRole('button', { name: '需要' }, { timeout: 10_000 }));

    expect(await screen.findByText('你剛改了題目，教練下一輪會先陪你回頭看第 4 階段還成不成立。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '換一個' })).not.toBeInTheDocument();
  });

  it('declines a candidate draft with 不需要 and keeps the card unchanged', { timeout: 40_000 }, async () => {
    const confirmed = { ...empty, pain_point: '預約很難排' };
    cardResponse = () => json({ stage: 1, version: 1, card: confirmed, pending: {
      card: { ...confirmed, candidates: ['校內外諮商預約整合'], ai_candidates: ['校內外諮商預約整合'] }, notes: ['加入候選'],
    }, history: [] });
    rejectResponse = () => json({ rejected: true, state: { stage: 1, version: 1, card: confirmed, pending: null, history: [] } });
    render(<Harness />);

    const draft = await screen.findByRole('group', { name: 'AI 幫你整理了以下候選題目，要列入下方「目前的題目」的候選清單嗎？' });
    expect(draft).toHaveTextContent('校內外諮商預約整合');
    fireEvent.click(screen.getByRole('button', { name: '不需要' }));

    await waitFor(() => expect(screen.queryByText('校內外諮商預約整合')).not.toBeInTheDocument());
    expect(JSON.parse(String(calls('/reject')[0][1]?.body))).toEqual({ version: 1 });
    expect(calls('/confirm')).toHaveLength(0);
    expect(screen.getByText('版本 v1')).toBeInTheDocument();
    expect(screen.getByText('預約很難排')).toBeInTheDocument();
  });

  it('keeps the chat working when the topic card API fails', { timeout: 40_000 }, async () => {
    cardResponse = () => json({ error: 'Topic card unavailable' }, 503);
    render(<Harness />);
    expect(await screen.findByText('題目卡暫時無法載入，對話不受影響。')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '我想找題目' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));

    await waitFor(() => expect(calls('/api/v1/stream')).toHaveLength(1), { timeout: 10_000 });
    expect(JSON.parse(String(calls('/api/v1/stream')[0][1]?.body)).conversation_kind).toBe('research_coach');
    await waitFor(() => expect(useChatStore.getState().messages.some((m) => m.role === 'assistant' && m.content.includes('痛點'))).toBe(true), { timeout: 10_000 });
  });
});
