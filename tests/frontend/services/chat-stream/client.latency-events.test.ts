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
    window.localStorage.clear();
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
    expect(payload.search_mode).toBe('never');
    expect(payload.use_web_search).toBe(false);
    expect(payload.interface_language).toBe('en');
    expect(payload.tutor_profile).toBe('general');
    expect(payload.response_mode).toBe('text');
    expect(onStatus).toHaveBeenCalledWith('retrieving', '正在整理相關脈絡');
    expect(onContent).toHaveBeenCalledWith('回答內容');
  });

  it('sends voice response mode when requested by live voice', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(['data: [DONE]\n\n'])));

    await createChatStream(
      [{ role: 'user', content: '請用語音說明' }],
      {
        onThinkingStart: vi.fn(), onThinkingContent: vi.fn(), onThinkingEnd: vi.fn(),
        onContent: vi.fn(), onCitations: vi.fn(), onDone: vi.fn(), onError: vi.fn(),
      },
      undefined,
      false,
      false,
      'never',
      'conversation-voice',
      [],
      { responseMode: 'voice' },
    );

    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body));
    expect(payload.response_mode).toBe('voice');
  });

  it('sends the selected tutor profile with stream requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(['data: [DONE]\n\n'])));

    await createChatStream(
      [{ role: 'user', content: 'Help me analyze Macbeth' }],
      {
        onThinkingStart: vi.fn(), onThinkingContent: vi.fn(), onThinkingEnd: vi.fn(),
        onContent: vi.fn(), onCitations: vi.fn(), onDone: vi.fn(), onError: vi.fn(),
      },
      undefined,
      false,
      false,
      'never',
      'conversation-english-tutor',
      [],
      { tutorProfile: 'english' },
    );

    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body));
    expect(payload.tutor_profile).toBe('english');
  });

  it('sends web-search routing flags for OpenRouter-backed search', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(['data: [DONE]\n\n'])));

    await createChatStream(
      [{ role: 'user', content: '請搜尋最新資料' }],
      {
        onThinkingStart: vi.fn(), onThinkingContent: vi.fn(), onThinkingEnd: vi.fn(),
        onContent: vi.fn(), onCitations: vi.fn(), onDone: vi.fn(), onError: vi.fn(),
      },
      undefined,
      false,
      false,
      'always',
      'conversation-web-search',
    );

    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body));
    expect(payload.conversation_id).toBe('conversation-web-search');
    expect(payload.search_mode).toBe('always');
    expect(payload.use_web_search).toBe(true);
    expect(payload.use_rag).toBe(false);
  });

  it('sends the selected interface language with stream requests', async () => {
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(['data: [DONE]\n\n'])));

    await createChatStream(
      [{ role: 'user', content: 'Explain this' }],
      {
        onThinkingStart: vi.fn(), onThinkingContent: vi.fn(), onThinkingEnd: vi.fn(),
        onContent: vi.fn(), onCitations: vi.fn(), onDone: vi.fn(), onError: vi.fn(),
      }
    );

    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body));
    expect(payload.interface_language).toBe('zh-TW');
  });

  it('uses FormData when the request includes attachments', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(['data: [DONE]\n\n'])));
    const attachment = new File(['attachment'], 'notes.txt', { type: 'text/plain' });

    await createChatStream(
      [{ role: 'user', content: '請摘要附件' }],
      {
        onThinkingStart: vi.fn(), onThinkingContent: vi.fn(), onThinkingEnd: vi.fn(),
        onContent: vi.fn(), onCitations: vi.fn(), onDone: vi.fn(), onError: vi.fn(),
      },
      undefined,
      false,
      false,
      'never',
      'conversation-1',
      [attachment],
    );

    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(request.body).toBeInstanceOf(FormData);
    expect((request.body as FormData).getAll('attachments')).toEqual([attachment]);
    expect((request.body as FormData).get('messages')).toContain('請摘要附件');
    expect((request.body as FormData).get('messages')).toContain('"interface_language":"en"');
    expect((request.body as FormData).get('messages')).toContain('"tutor_profile":"general"');
  });

  it('preserves web-search routing flags in multipart attachment requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(['data: [DONE]\n\n'])));
    const attachment = new File(['attachment'], 'notes.txt', { type: 'text/plain' });

    await createChatStream(
      [{ role: 'user', content: '請搜尋並分析附件' }],
      {
        onThinkingStart: vi.fn(), onThinkingContent: vi.fn(), onThinkingEnd: vi.fn(),
        onContent: vi.fn(), onCitations: vi.fn(), onDone: vi.fn(), onError: vi.fn(),
      },
      undefined,
      false,
      false,
      'always',
      'conversation-web-search-file',
      [attachment],
      { tutorProfile: 'english' },
    );

    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const formData = request.body as FormData;
    const payload = JSON.parse(String(formData.get('messages')));
    expect(formData.getAll('attachments')).toEqual([attachment]);
    expect(payload.search_mode).toBe('always');
    expect(payload.tutor_profile).toBe('english');
    expect(payload.use_web_search).toBe(true);
    expect(payload.use_rag).toBe(false);
  });

  it('dispatches structured answer blocks from SSE', async () => {
    const blocks = [{ type: 'paragraph', text: '第一段' }];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          `event: answer_blocks\ndata: ${JSON.stringify(blocks)}\n\n`,
          'data: [DONE]\n\n',
        ])
      )
    );
    const onAnswerBlocks = vi.fn();

    await createChatStream(
      [{ role: 'user', content: '請圖解' }],
      {
        onThinkingStart: vi.fn(),
        onThinkingContent: vi.fn(),
        onThinkingEnd: vi.fn(),
        onContent: vi.fn(),
        onCitations: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
        onAnswerBlocks,
      }
    );

    expect(onAnswerBlocks).toHaveBeenCalledWith(blocks);
  });

  it('dispatches only validated privacy-safe image slot metadata', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          'event: image_slot\ndata: {"slotId":"img_1","anchorAfterParagraph":1,"contentOffset":12}\n\n',
          'event: image_slot\ndata: {"slotId":"","anchorAfterParagraph":-1,"contentOffset":"bad"}\n\n',
          'data: [DONE]\n\n',
        ])
      )
    );
    const onImageSlot = vi.fn();

    await createChatStream(
      [{ role: 'user', content: '請圖解' }],
      {
        onThinkingStart: vi.fn(),
        onThinkingContent: vi.fn(),
        onThinkingEnd: vi.fn(),
        onContent: vi.fn(),
        onCitations: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
        onImageSlot,
      }
    );

    expect(onImageSlot).toHaveBeenCalledOnce();
    expect(onImageSlot).toHaveBeenCalledWith({
      slotId: 'img_1',
      anchorAfterParagraph: 1,
      contentOffset: 12,
    });
  });
});
