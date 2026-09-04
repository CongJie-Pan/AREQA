import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { startRealtimeClient } from '@/services/realtime/client';

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));

class FakeDataChannel {
  readyState = 'open';
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  close = vi.fn(() => {
    this.readyState = 'closed';
  });
  send = vi.fn();
}

let lastPeerConnection: FakePeerConnection | null = null;

class FakePeerConnection {
  connectionState = 'new';
  ontrack: ((event: { streams: MediaStream[] }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  channel = new FakeDataChannel();
  createDataChannel = vi.fn(() => this.channel);
  addTrack = vi.fn();
  createOffer = vi.fn(async () => ({ type: 'offer', sdp: 'offer-sdp' }));
  setLocalDescription = vi.fn(async () => undefined);
  setRemoteDescription = vi.fn(async () => undefined);
  close = vi.fn();

  constructor() {
    lastPeerConnection = this;
  }
}

function realtimeOptions(overrides: Partial<Parameters<typeof startRealtimeClient>[0]> = {}) {
  return {
    conversationId: 'conv_123',
    interfaceLanguage: 'zh-TW' as const,
    recentMessages: () => [],
    onRemoteStream: vi.fn(),
    onStatus: vi.fn(),
    onUserTranscript: vi.fn(),
    onAssistantTranscriptDelta: vi.fn(),
    onAssistantTranscriptDone: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

describe('Realtime client lifecycle', () => {
  const originalPeerConnection = globalThis.RTCPeerConnection;
  const originalFetch = globalThis.fetch;
  const originalNavigator = globalThis.navigator;

  beforeEach(() => {
    vi.clearAllMocks();
    lastPeerConnection = null;
    Object.defineProperty(globalThis, 'RTCPeerConnection', {
      configurable: true,
      value: FakePeerConnection,
    });
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: vi.fn(async () => new Response('answer-sdp', { status: 200 })),
    });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'RTCPeerConnection', {
      configurable: true,
      value: originalPeerConnection,
    });
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: originalFetch,
    });
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: originalNavigator,
    });
  });

  it('does not create a provider session when microphone permission is denied', async () => {
    const permissionError = new DOMException('Permission denied', 'NotAllowedError');
    const options = realtimeOptions();
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        mediaDevices: {
          getUserMedia: vi.fn(async () => {
            throw permissionError;
          }),
        },
      },
    });

    await startRealtimeClient(options);

    expect(authenticatedFetch).not.toHaveBeenCalled();
    expect(options.onError).toHaveBeenCalledWith(expect.objectContaining({
      message: 'Microphone permission denied',
    }));
  });

  it('stops microphone tracks when session creation fails after permission succeeds', async () => {
    const stop = vi.fn();
    const track = { stop, enabled: true };
    const stream = {
      getTracks: () => [track],
      getAudioTracks: () => [track],
    } as unknown as MediaStream;
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        mediaDevices: {
          getUserMedia: vi.fn(async () => stream),
        },
      },
    });
    vi.mocked(authenticatedFetch).mockResolvedValue(
      new Response(JSON.stringify({ error: { message: 'rate limited' } }), {
        status: 429,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await startRealtimeClient(realtimeOptions());

    expect(stop).toHaveBeenCalledTimes(1);
  });

  it('emits assistant response boundaries before a new response appends transcript deltas', async () => {
    const stop = vi.fn();
    const track = { stop, enabled: true };
    const stream = {
      getTracks: () => [track],
      getAudioTracks: () => [track],
    } as unknown as MediaStream;
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        mediaDevices: {
          getUserMedia: vi.fn(async () => stream),
        },
      },
    });
    vi.mocked(authenticatedFetch).mockResolvedValue(
      new Response(JSON.stringify({
        client_secret: 'ek_test',
        model: 'gpt-realtime-2.1-mini',
        voice: 'marin',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const onAssistantResponseStarted = vi.fn();
    const onAssistantTranscriptDelta = vi.fn();

    await startRealtimeClient(realtimeOptions({
      onAssistantResponseStarted,
      onAssistantTranscriptDelta,
    }));
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.created' }),
    });
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.audio_transcript.delta', delta: 'new answer' }),
    });
    await vi.waitFor(() => {
      expect(onAssistantTranscriptDelta).toHaveBeenCalledWith('new answer');
    });

    expect(onAssistantResponseStarted.mock.invocationCallOrder[0]).toBeLessThan(
      onAssistantTranscriptDelta.mock.invocationCallOrder[0],
    );
  });
});
