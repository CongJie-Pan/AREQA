import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatInput } from '@/components/ChatInput';
import { createChatStream } from '@/services/chat-stream/client';
import { useChatStore } from '@/store/chat';

vi.mock('@/database/db', () => ({
  getAuthToken: vi.fn(() => 'test-token'),
  getCurrentUserId: vi.fn(() => 'user-1'),
}));

vi.mock('@/services/speech/transcription', () => ({
  transcribeSpeech: vi.fn(),
}));

vi.mock('@/config/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/api')>();
  return {
    ...actual,
    API_CONFIG: {
      ...actual.API_CONFIG,
      chatEndpoint: 'http://frontend-integration.test/api/v1/stream',
    },
  };
});

function doneStream(): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode('data: [DONE]\n\n'));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

async function sendThroughStream(message: string): Promise<void> {
  await createChatStream(
    [{ role: 'user', content: message }],
    {
      onThinkingStart: vi.fn(),
      onThinkingContent: vi.fn(),
      onThinkingEnd: vi.fn(),
      onContent: vi.fn(),
      onCitations: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    },
    undefined,
    false,
    false,
    useChatStore.getState().searchMode,
    'explicit-web-search-flow',
  );
}

describe('explicit web search chat flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useChatStore.setState({ useRag: false, useWebSearch: false, searchMode: 'never' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(doneStream()));
  });

  it('sends web search only after the globe button is enabled', async () => {
    render(<ChatInput onSend={sendThroughStream} />);

    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '今天最新新聞' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    let request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    let payload = JSON.parse(String(request.body));
    expect(payload.search_mode).toBe('never');
    expect(payload.use_web_search).toBe(false);

    const globeButton = screen.getByLabelText('開啟網路搜尋');
    fireEvent.click(globeButton);
    expect(useChatStore.getState().searchMode).toBe('always');

    fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '請搜尋 OpenRouter 最新文件' } });
    fireEvent.click(screen.getByLabelText('發送訊息'));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    request = vi.mocked(fetch).mock.calls[1][1] as RequestInit;
    payload = JSON.parse(String(request.body));
    expect(payload.search_mode).toBe('always');
    expect(payload.use_web_search).toBe(true);
  });
});
