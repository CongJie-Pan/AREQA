import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils', () => ({
  checkRateLimit: vi.fn(() => ({ allowed: true, remaining: 19, limit: 20, resetIn: 60 })),
  getClientIdentifier: vi.fn(() => 'test-client-id'),
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('next/server', () => ({
  NextResponse: {
    json: (body: unknown, init?: ResponseInit) => new Response(JSON.stringify(body), init),
  },
}));

import { POST } from '@/app/api/speech/read/route';
import { checkRateLimit } from '@/utils';

function jsonRequest(body: unknown) {
  return {
    json: async () => body,
    signal: new AbortController().signal,
  };
}

describe('speech read aloud API route', () => {
  const originalOpenAiApiKey = process.env.OPENAI_API_KEY;
  const originalOpenAiTtsModel = process.env.OPENAI_TTS_MODEL;
  const originalOpenAiTtsVoice = process.env.OPENAI_TTS_VOICE;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.OPENAI_API_KEY = 'test-openai-key';
    delete process.env.OPENAI_TTS_MODEL;
    delete process.env.OPENAI_TTS_VOICE;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('mp3-bytes', {
          status: 200,
          headers: { 'content-type': 'audio/mpeg' },
        }),
      ),
    );
  });

  afterEach(() => {
    process.env.OPENAI_API_KEY = originalOpenAiApiKey;
    process.env.OPENAI_TTS_MODEL = originalOpenAiTtsModel;
    process.env.OPENAI_TTS_VOICE = originalOpenAiTtsVoice;
    vi.unstubAllGlobals();
  });

  it('generates assistant read-out audio through OpenAI TTS', async () => {
    const response = await POST(jsonRequest({ text: '請朗讀這段回覆' }) as any);
    const requestInit = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(requestInit.body));

    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('audio/mpeg');
    expect(fetch).toHaveBeenCalledWith(
      'https://api.openai.com/v1/audio/speech',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-openai-key',
          'Content-Type': 'application/json',
        }),
      }),
    );
    expect(body).toMatchObject({
      model: 'gpt-4o-mini-tts',
      voice: 'cedar',
      input: '請朗讀這段回覆',
      response_format: 'mp3',
    });
  });

  it('fails softly when OpenAI TTS is not configured', async () => {
    delete process.env.OPENAI_API_KEY;

    const response = await POST(jsonRequest({ text: 'hello' }) as any);
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload.error.code).toBe('TTS_NOT_CONFIGURED');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rate limits read-out generation', async () => {
    vi.mocked(checkRateLimit).mockReturnValue({ allowed: false, remaining: 0, limit: 20, resetIn: 60 });

    const response = await POST(jsonRequest({ text: 'hello' }) as any);
    const payload = await response.json();

    expect(response.status).toBe(429);
    expect(payload.error.code).toBe('RATE_LIMITED');
    expect(fetch).not.toHaveBeenCalled();
  });
});
