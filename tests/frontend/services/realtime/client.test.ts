import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { RealtimeClientError, startRealtimeClient } from '@/services/realtime/client';

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
let lastWebSocket: FakeWebSocket | null = null;
let lastScriptProcessor: FakeScriptProcessor | null = null;

class FakePeerConnection {
  connectionState = 'new';
  ontrack: ((event: { streams: MediaStream[]; track: { kind: string } }) => void) | null = null;
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

class FakeScriptProcessor {
  onaudioprocess: ((event: AudioProcessingEvent) => void) | null = null;
  connect = vi.fn();
  disconnect = vi.fn();
}

class FakeAudioBufferSource {
  buffer: AudioBuffer | null = null;
  onended: (() => void) | null = null;
  connect = vi.fn();
  disconnect = vi.fn();
  start = vi.fn(() => {
    this.onended?.();
  });
  stop = vi.fn();
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  static suspendOutputContext = false;
  sampleRate = 48000;
  currentTime = 0;
  state: AudioContextState = 'running';
  destination = {};
  close = vi.fn(async () => undefined);
  resume = vi.fn(async () => undefined);
  createMediaStreamSource = vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
  }));
  createScriptProcessor = vi.fn(() => {
    lastScriptProcessor = new FakeScriptProcessor();
    return lastScriptProcessor;
  });
  createBuffer = vi.fn((_channels: number, length: number, sampleRate: number) => ({
    duration: length / sampleRate,
    copyToChannel: vi.fn(),
  }));
  createBufferSource = vi.fn(() => new FakeAudioBufferSource());

  constructor(options?: AudioContextOptions) {
    if (options?.sampleRate) this.sampleRate = options.sampleRate;
    if (options?.sampleRate === 24000 && FakeAudioContext.suspendOutputContext) {
      this.state = 'suspended';
    }
    FakeAudioContext.instances.push(this);
  }
}

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code: 1000, wasClean: true } as CloseEvent);
  });

  constructor(public readonly url: string, public readonly protocols?: string | string[]) {
    lastWebSocket = this;
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  receive(event: object): void {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent);
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

function installMicrophone(options: {
  userAgent?: string;
  platform?: string;
  maxTouchPoints?: number;
} = {}): { stream: MediaStream; stop: ReturnType<typeof vi.fn> } {
  const stop = vi.fn();
  const track = { stop, enabled: true };
  const stream = {
    getTracks: () => [track],
    getAudioTracks: () => [track],
  } as unknown as MediaStream;
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      userAgent: options.userAgent ?? 'Mozilla/5.0 (X11; Linux x86_64)',
      platform: options.platform ?? 'Linux x86_64',
      maxTouchPoints: options.maxTouchPoints ?? 0,
      mediaDevices: {
        getUserMedia: vi.fn(async () => stream),
      },
    },
  });
  return { stream, stop };
}

function emitMicrophoneFrame(samples: Float32Array): void {
  lastScriptProcessor?.onaudioprocess?.({
    inputBuffer: { getChannelData: () => samples },
    outputBuffer: { getChannelData: () => new Float32Array(samples.length) },
  } as AudioProcessingEvent);
}

function mockRealtimeSession(): void {
  vi.mocked(authenticatedFetch).mockResolvedValueOnce(
    new Response(JSON.stringify({
      client_secret: 'ek_test',
      model: 'gpt-realtime-2.1-mini',
      voice: 'marin',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

describe('Realtime client lifecycle', () => {
  it('seeds role-preserving history when the channel opens, before speech responses', async () => {
    installMicrophone();
    mockRealtimeSession();
    const options = realtimeOptions({ recentMessages: () => [
      { id: 'u1', conversationId: 'conv_123', userId: 'guest', role: 'user', content: 'Explain paper A', createdAt: new Date() },
      { id: 'a1', conversationId: 'conv_123', userId: 'guest', role: 'assistant', content: 'Paper A studies learning.', createdAt: new Date() },
    ] });
    const controller = await startRealtimeClient(options);
    lastPeerConnection?.channel.onopen?.();
    const events = lastPeerConnection?.channel.send.mock.calls.map(([body]) => JSON.parse(body));
    expect(events?.map((event) => event.item.role)).toEqual(['user', 'assistant']);
    expect(events?.[1].item.content[0]).toEqual({ type: 'output_text', text: 'Paper A studies learning.' });
    controller.disconnect();
  });

  it('reports playback independently of generation completion and binds late transcripts to their turn', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onPlaybackState = vi.fn();
    const onUserTurnCommitted = vi.fn();
    const options = realtimeOptions({ onPlaybackState, onUserTurnCommitted });
    const controller = await startRealtimeClient(options);
    const send = (event: object) => lastPeerConnection?.channel.onmessage?.({ data: JSON.stringify(event) });
    send({ type: 'input_audio_buffer.committed', item_id: 'turn1' });
    send({ type: 'output_audio_buffer.started' });
    send({ type: 'response.done' });
    expect(onPlaybackState.mock.calls).toEqual([['started']]);
    send({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'turn1', transcript: '問題' });
    expect(options.onUserTranscript).toHaveBeenCalledWith('問題', 'turn1');
    expect(onUserTurnCommitted).toHaveBeenCalledWith('turn1');
    send({ type: 'output_audio_buffer.stopped' });
    expect(onPlaybackState).toHaveBeenLastCalledWith('stopped');
    controller.disconnect();
  });

  it('routes remote video tracks separately so avatar media can render without replacing audio playback', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onRemoteStream = vi.fn();
    const onRemoteVideoStream = vi.fn();
    const avatarStream = {
      getAudioTracks: () => [],
      getVideoTracks: () => [{ readyState: 'live' }],
    } as unknown as MediaStream;

    const controller = await startRealtimeClient(realtimeOptions({ onRemoteStream, onRemoteVideoStream }));
    lastPeerConnection?.ontrack?.({ streams: [avatarStream], track: { kind: 'video' } });

    expect(onRemoteVideoStream).toHaveBeenCalledWith(avatarStream);
    expect(onRemoteStream).not.toHaveBeenCalled();
    controller.disconnect();
  });

  it('does not send response.cancel while no realtime response is active', async () => {
    installMicrophone();
    mockRealtimeSession();
    const controller = await startRealtimeClient(realtimeOptions());

    controller.disconnect();

    const sentEvents = lastPeerConnection?.channel.send.mock.calls.map(([body]) => JSON.parse(body));
    expect(sentEvents).not.toContainEqual(expect.objectContaining({ type: 'response.cancel' }));
  });

  it('notifies the app when user speech starts so stale chat streams can be cancelled', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onUserSpeechStarted = vi.fn();
    const onPlaybackState = vi.fn();
    await startRealtimeClient(realtimeOptions({ onUserSpeechStarted, onPlaybackState }));

    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'input_audio_buffer.speech_started' }),
    });

    expect(onUserSpeechStarted).toHaveBeenCalledOnce();
    expect(onPlaybackState).toHaveBeenCalledWith('interrupted');
  });

  it('can cancel realtime speech without closing the data channel', async () => {
    installMicrophone();
    mockRealtimeSession();
    const controller = await startRealtimeClient(realtimeOptions());

    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.created', response: { id: 'resp_123' } }),
    });
    controller.cancelSpeech();

    expect(lastPeerConnection?.channel.send).toHaveBeenCalledWith(JSON.stringify({
      type: 'response.cancel',
      response_id: 'resp_123',
    }));
    expect(lastPeerConnection?.channel.close).not.toHaveBeenCalled();
    controller.disconnect();
  });

  it('clears active output audio during cancellation without requiring an active response', async () => {
    installMicrophone();
    mockRealtimeSession();
    const controller = await startRealtimeClient(realtimeOptions());

    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'output_audio_buffer.started' }),
    });
    controller.cancelSpeech();

    expect(lastPeerConnection?.channel.send).toHaveBeenCalledWith(JSON.stringify({
      type: 'output_audio_buffer.clear',
    }));
    controller.disconnect();
  });

  it('uses the websocket transport when flagged and owns audio playback events', async () => {
    vi.stubEnv('NEXT_PUBLIC_LIVE_VOICE_TRANSPORT', 'websocket');
    installMicrophone();
    mockRealtimeSession();
    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      value: FakeWebSocket,
    });
    Object.defineProperty(globalThis, 'AudioContext', {
      configurable: true,
      value: FakeAudioContext,
    });
    const onPlaybackState = vi.fn();
    const onAssistantTranscriptDelta = vi.fn();
    const onAssistantTranscriptDone = vi.fn();
    const controller = await startRealtimeClient(realtimeOptions({
      recentMessages: () => [
        { id: 'u1', conversationId: 'conv_123', userId: 'guest', role: 'user', content: '你好', createdAt: new Date() },
      ],
      onPlaybackState,
      onAssistantTranscriptDelta,
      onAssistantTranscriptDone,
    }));

    lastWebSocket?.open();
    expect(lastPeerConnection).toBeNull();
    expect(lastWebSocket?.url).toBe('wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1-mini');
    expect(lastWebSocket?.protocols).toEqual([
      'realtime',
      'openai-insecure-api-key.ek_test',
    ]);
    expect(lastWebSocket?.send).toHaveBeenCalledWith(expect.stringContaining('"conversation.item.create"'));

    lastWebSocket?.receive({ type: 'response.created', response: { id: 'resp_ws' } });
    lastWebSocket?.receive({ type: 'response.output_audio.delta', delta: 'AAAAAA==' });
    lastWebSocket?.receive({ type: 'response.output_audio_transcript.delta', delta: '你好' });
    lastWebSocket?.receive({ type: 'response.output_audio_transcript.done', transcript: '你好' });

    await vi.waitFor(() => expect(onAssistantTranscriptDone).toHaveBeenCalledWith('你好'));
    expect(onPlaybackState).toHaveBeenCalledWith('started');
    expect(onAssistantTranscriptDelta).toHaveBeenCalledWith('你好');
    controller.disconnect();
  });

  it('falls back to webrtc on mobile even when websocket transport is flagged', async () => {
    vi.stubEnv('NEXT_PUBLIC_LIVE_VOICE_TRANSPORT', 'websocket');
    installMicrophone({
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148',
      platform: 'iPhone',
      maxTouchPoints: 5,
    });
    mockRealtimeSession();
    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      value: FakeWebSocket,
    });

    const controller = await startRealtimeClient(realtimeOptions());

    expect(lastWebSocket).toBeNull();
    expect(lastPeerConnection).not.toBeNull();
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    controller.disconnect();
  });

  it('resumes websocket output audio and suppresses microphone echo while assistant audio plays', async () => {
    vi.stubEnv('NEXT_PUBLIC_LIVE_VOICE_TRANSPORT', 'websocket');
    FakeAudioContext.suspendOutputContext = true;
    installMicrophone();
    mockRealtimeSession();
    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      value: FakeWebSocket,
    });
    Object.defineProperty(globalThis, 'AudioContext', {
      configurable: true,
      value: FakeAudioContext,
    });

    const controller = await startRealtimeClient(realtimeOptions());
    lastWebSocket?.open();
    lastWebSocket?.send.mockClear();

    lastWebSocket?.receive({ type: 'response.created', response: { id: 'resp_ws' } });
    lastWebSocket?.receive({ type: 'response.output_audio.delta', delta: 'AAAAAA==' });
    emitMicrophoneFrame(new Float32Array(8192).fill(0.5));

    expect(FakeAudioContext.instances[1]?.resume).toHaveBeenCalledOnce();
    expect(lastWebSocket?.send).not.toHaveBeenCalledWith(expect.stringContaining('"input_audio_buffer.append"'));
    controller.disconnect();
  });

  const originalPeerConnection = globalThis.RTCPeerConnection;
  const originalFetch = globalThis.fetch;
  const originalNavigator = globalThis.navigator;
  const originalWebSocket = globalThis.WebSocket;
  const originalAudioContext = globalThis.AudioContext;

  beforeEach(() => {
    vi.clearAllMocks();
    lastPeerConnection = null;
    lastWebSocket = null;
    lastScriptProcessor = null;
    FakeAudioContext.instances = [];
    FakeAudioContext.suspendOutputContext = false;
    vi.unstubAllEnvs();
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
    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      value: originalWebSocket,
    });
    Object.defineProperty(globalThis, 'AudioContext', {
      configurable: true,
      value: originalAudioContext,
    });
    vi.unstubAllEnvs();
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
      code: 'microphone_denied',
      message: 'Microphone permission denied',
    }));
  });

  it('stops microphone tracks when session creation fails after permission succeeds', async () => {
    const { stop } = installMicrophone();
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
    installMicrophone();
    mockRealtimeSession();
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

  it('supports current output-audio transcript events without duplicating the final response', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onAssistantTranscriptDelta = vi.fn();
    const onAssistantTranscriptDone = vi.fn();

    await startRealtimeClient(realtimeOptions({
      onAssistantTranscriptDelta,
      onAssistantTranscriptDone,
    }));
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.created' }),
    });
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.output_audio_transcript.delta', delta: '這是回答' }),
    });
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.output_audio_transcript.done', transcript: '這是回答' }),
    });
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({
        type: 'response.done',
        response: {
          output: [{
            type: 'message',
            role: 'assistant',
            content: [{ type: 'audio', transcript: '這是回答' }],
          }],
        },
      }),
    });

    await vi.waitFor(() => expect(onAssistantTranscriptDone).toHaveBeenCalledOnce());
    expect(onAssistantTranscriptDelta).toHaveBeenCalledWith('這是回答');
    expect(onAssistantTranscriptDone).toHaveBeenCalledWith('這是回答');
  });

  it('recovers assistant text from response.done when no transcript deltas arrive', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onAssistantTranscriptDone = vi.fn();

    await startRealtimeClient(realtimeOptions({ onAssistantTranscriptDone }));
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.created' }),
    });
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({
        type: 'response.done',
        response: {
          output: [{
            type: 'message',
            role: 'assistant',
            content: [{ type: 'audio', transcript: '完整語音回覆' }],
          }],
        },
      }),
    });

    await vi.waitFor(() => {
      expect(onAssistantTranscriptDone).toHaveBeenCalledWith('完整語音回覆');
    });
  });

  it('accepts authoritative text from a done-only text event', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onAssistantTranscriptDone = vi.fn();

    await startRealtimeClient(realtimeOptions({ onAssistantTranscriptDone }));
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.created' }),
    });
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.output_text.done', text: '純文字回覆' }),
    });

    await vi.waitFor(() => {
      expect(onAssistantTranscriptDone).toHaveBeenCalledWith('純文字回覆');
    });
  });

  it('completes one context tool call once when both provider completion events arrive', async () => {
    installMicrophone();
    mockRealtimeSession();
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ recent_messages: [], memory_items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const recentMessages = () => [{
      id: 'message-1',
      userId: 'user-1',
      conversationId: 'conv_123',
      role: 'user' as const,
      content: '請解釋這篇論文',
      attachments: [{ name: 'paper.pdf', mediaType: 'application/pdf', sizeBytes: 123 }],
      createdAt: new Date(),
    }];

    await startRealtimeClient(realtimeOptions({ recentMessages }));
    const functionCall = {
      call_id: 'call_123',
      name: 'get_areqa_context',
    };
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.function_call_arguments.done', ...functionCall }),
    });
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({ type: 'response.output_item.done', item: { type: 'function_call', ...functionCall } }),
    });

    await vi.waitFor(() => expect(lastPeerConnection?.channel.send).toHaveBeenCalledTimes(2));
    expect(authenticatedFetch).toHaveBeenCalledTimes(2);
    const contextRequest = vi.mocked(authenticatedFetch).mock.calls[1]?.[1];
    expect(String(contextRequest?.body)).toContain('paper.pdf');
    expect(lastPeerConnection?.channel.send).toHaveBeenLastCalledWith(expect.stringContaining('"tool_choice":"none"'));
  });

  it('surfaces a stable provider error code without exposing the provider message', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onError = vi.fn();

    await startRealtimeClient(realtimeOptions({ onError }));
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({
        type: 'error',
        error: {
          type: 'invalid_request_error',
          code: 'conversation_already_has_active_response',
          message: 'sensitive provider details',
        },
      }),
    });

    await vi.waitFor(() => expect(onError).toHaveBeenCalledOnce());
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      code: 'provider_error',
      message: 'Realtime provider error (conversation_already_has_active_response)',
    } satisfies Partial<RealtimeClientError>));
  });

  it('ignores non-fatal response_cancel_not_active provider errors', async () => {
    installMicrophone();
    mockRealtimeSession();
    const onError = vi.fn();

    await startRealtimeClient(realtimeOptions({ onError }));
    lastPeerConnection?.channel.onmessage?.({
      data: JSON.stringify({
        type: 'error',
        error: {
          type: 'invalid_request_error',
          code: 'response_cancel_not_active',
          message: 'No active response to cancel',
        },
      }),
    });

    expect(onError).not.toHaveBeenCalled();
  });

});
