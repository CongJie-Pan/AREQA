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

function installMicrophone(): { stream: MediaStream; stop: ReturnType<typeof vi.fn> } {
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
  return { stream, stop };
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

  it('cancels the active realtime response before disconnecting', async () => {
    installMicrophone();
    mockRealtimeSession();
    const controller = await startRealtimeClient(realtimeOptions());

    controller.disconnect();

    const sentEvents = lastPeerConnection?.channel.send.mock.calls.map(([body]) => JSON.parse(body));
    expect(sentEvents).toContainEqual({ type: 'response.cancel' });
  });

  it('renders AREQA-authored answers as out-of-band realtime audio', async () => {
    installMicrophone();
    mockRealtimeSession();
    const controller = await startRealtimeClient(realtimeOptions());

    controller.speakAreqaAnswer('這是 AREQA 的正式回答。');

    const sentEvents = lastPeerConnection?.channel.send.mock.calls.map(([body]) => JSON.parse(body));
    const speechEvent = sentEvents?.find((event) => event.type === 'response.create');
    expect(speechEvent).toMatchObject({
      type: 'response.create',
      response: {
        conversation: 'none',
        output_modalities: ['audio'],
        tools: [],
        metadata: { response_purpose: 'areqa_voice_render' },
      },
    });
    expect(speechEvent?.response.input[0].content[0].text).toContain('這是 AREQA 的正式回答。');
    controller.disconnect();
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

    controller.cancelSpeech();

    expect(lastPeerConnection?.channel.send).toHaveBeenCalledWith(JSON.stringify({ type: 'response.cancel' }));
    expect(lastPeerConnection?.channel.close).not.toHaveBeenCalled();
    controller.disconnect();
  });
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
});
