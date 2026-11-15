import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { createReadAloudAudio, prepareReadAloudText, startReadAloudPlayback } from '@/services/speech/readAloud';

/** Minimal Media Source stand-in: opens on creation and records appended chunks. */
class FakeSourceBuffer extends EventTarget {
  appended: number[][] = [];
  buffered = { length: 0, start: () => 0, end: () => 0 };
  appendBuffer(chunk: Uint8Array) {
    this.appended.push(Array.from(chunk));
    setTimeout(() => this.dispatchEvent(new Event('updateend')), 0);
  }
  remove() {
    setTimeout(() => this.dispatchEvent(new Event('updateend')), 0);
  }
}

class FakeMediaSource extends EventTarget {
  static instances: FakeMediaSource[] = [];
  static isTypeSupported = vi.fn((type: string) => type === 'audio/mpeg');
  readyState: 'closed' | 'open' | 'ended' = 'closed';
  buffer = new FakeSourceBuffer();
  constructor() {
    super();
    FakeMediaSource.instances.push(this);
    setTimeout(() => {
      this.readyState = 'open';
      this.dispatchEvent(new Event('sourceopen'));
    }, 0);
  }
  addSourceBuffer() {
    return this.buffer;
  }
  endOfStream() {
    this.readyState = 'ended';
  }
}

/** A response body whose chunks are released one at a time by the test. */
function controlledBody() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const state = { cancelled: false };
  const body = new ReadableStream<Uint8Array>({
    start(c) { controller = c; },
    cancel() { state.cancelled = true; },
  });
  return {
    body, state,
    push: (bytes: number[]) => controller.enqueue(new Uint8Array(bytes)),
    end: () => controller.close(),
  };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 5));

describe('readAloud speech service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    FakeMediaSource.instances = [];
    URL.createObjectURL = vi.fn(() => 'blob:read-aloud');
    URL.revokeObjectURL = vi.fn();
  });

  it('starts playback from the first chunk when the browser can stream MP3', async () => {
    vi.stubGlobal('MediaSource', FakeMediaSource);
    const { body, push, end } = controlledBody();
    vi.mocked(authenticatedFetch).mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'audio/mpeg' } }),
    );

    const playback = await startReadAloudPlayback('請讀 **這段**');
    expect(playback.mode).toBe('stream');
    expect(playback.audio.src).toBe('blob:read-aloud');

    push([1, 2]);
    await flush();
    // The first chunk is playable while the rest is still being generated.
    expect(FakeMediaSource.instances[0].buffer.appended).toEqual([[1, 2]]);
    expect(FakeMediaSource.instances[0].readyState).toBe('open');

    push([3]);
    end();
    await flush();
    expect(FakeMediaSource.instances[0].buffer.appended).toEqual([[1, 2], [3]]);
    expect(FakeMediaSource.instances[0].readyState).toBe('ended');

    playback.dispose();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:read-aloud');
  });

  it('stops downloading when playback is disposed mid-stream', async () => {
    vi.stubGlobal('MediaSource', FakeMediaSource);
    const { body, push, state } = controlledBody();
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(body, { status: 200 }));

    const playback = await startReadAloudPlayback('請讀');
    push([1]);
    await flush();
    playback.dispose();
    await flush();

    expect(state.cancelled).toBe(true);
    expect(FakeMediaSource.instances[0].buffer.appended).toEqual([[1]]);
  });

  it('falls back to a downloaded blob when MP3 streaming is unsupported', async () => {
    vi.stubGlobal('MediaSource', undefined);
    vi.mocked(authenticatedFetch).mockResolvedValue(
      new Response(new Blob(['audio'], { type: 'audio/mpeg' }), { status: 200 }),
    );

    const playback = await startReadAloudPlayback('請讀');

    expect(playback.mode).toBe('buffered');
    expect(playback.audio.src).toBe('blob:read-aloud');
    playback.dispose();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:read-aloud');
  });

  it('rejects when the speech API fails so the player can show an error', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(null, { status: 503 }));
    await expect(startReadAloudPlayback('請讀')).rejects.toThrow('Read aloud failed');
  });

  it('normalizes markdown into readable text', () => {
    expect(prepareReadAloudText('## 重點\n\n請讀 **這段** [內容](https://example.com)。')).toBe('重點\n\n請讀 這段 內容。');
  });

  it('posts readable text to the configured speech endpoint', async () => {
    const signal = new AbortController().signal;
    vi.mocked(authenticatedFetch).mockResolvedValue(
      new Response(new Blob(['audio'], { type: 'audio/mpeg' }), { status: 200 }),
    );

    await createReadAloudAudio('請讀 **這段**', signal);

    expect(authenticatedFetch).toHaveBeenCalledWith('/api/speech/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: '請讀 這段' }),
      signal,
    });
  });
});
