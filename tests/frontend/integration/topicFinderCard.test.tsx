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
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      const target = String(url);
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
    expect(await screen.findByRole('note', {}, { timeout: 10_000 })).toHaveTextContent('系統和 Gemini 差不多');
    // The draft does not move the learner: they are still at stage 1.
    expect(screen.getByText('第 1 階段')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '採用這份整理' }));

    await waitFor(() => expect(screen.getByText('版本 v1')).toBeInTheDocument());
    expect(screen.getByText('第 1 階段')).toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(JSON.parse(String(calls('/confirm')[0][1]?.body))).toEqual({ version: 0 });
    expect(calls('/stage')).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: '下一階段 →' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '有沒有很簡單的解法？' })).toBeInTheDocument());
    expect(JSON.parse(String(calls('/stage')[0][1]?.body))).toEqual({ stage: 2 });
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
