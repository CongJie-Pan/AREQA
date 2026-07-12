import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createChatStream } from '@/services/chat-stream/client';


const setTokenUsage = vi.fn();

vi.mock('@/database/db', () => ({
  getAuthToken: vi.fn(() => 'benchmark-token'),
}));

vi.mock('@/store/chat/store', () => ({
  useChatStore: {
    getState: vi.fn(() => ({ setTokenUsage })),
  },
}));

vi.mock('@/config/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/api')>();
  return {
    ...actual,
    API_CONFIG: {
      ...actual.API_CONFIG,
      chatEndpoint: 'http://benchmark.test/api/v1/stream',
    },
  };
});

function streamResponse(blocks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const block of blocks) controller.enqueue(encoder.encode(block));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe('chat stream visible latency events', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps metadata invisible and exposes status before answer content', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          'event: metadata\ndata: {"promptTokens":10,"completionTokens":0,"totalTokens":10}\n\n',
          'event: status\ndata: {"status":"retrieving","message":"正在整理相關脈絡"}\n\n',
          'event: action\ndata: {"action":"answer_directly","display_message":"正在整理回答脈絡"}\n\n',
          'event: future_event\ndata: {"schema_version":99,"unknown":true}\n\n',
          'data: {"choices":[{"delta":{"content":"回答內容"}}]}\n\n',
          'data: [DONE]\n\n',
        ])
      )
    );
    const order: string[] = [];
    const onStatus = vi.fn(() => order.push('status'));
    const onContent = vi.fn(() => order.push('content'));
    const onDone = vi.fn(() => order.push('done'));

    await createChatStream(
      [{ role: 'user', content: '測試問題' }],
      {
        onThinkingStart: vi.fn(),
        onThinkingContent: vi.fn(),
        onThinkingEnd: vi.fn(),
        onContent,
        onCitations: vi.fn(),
        onDone,
        onError: vi.fn(),
        onStatus,
      }
    );

    expect(setTokenUsage).toHaveBeenCalledOnce();
    expect(order).toEqual(['status', 'status', 'content', 'done']);
    expect(onStatus).toHaveBeenLastCalledWith('routing', '正在整理回答脈絡');
    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body));
    expect(payload.search_mode).toBe('auto');
    expect(payload.use_web_search).toBe(false);
    expect(onStatus).toHaveBeenCalledWith('retrieving', '正在整理相關脈絡');
    expect(onContent).toHaveBeenCalledWith('回答內容');
  });
});
