import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import {
  __setLiveKitClientLoaderForTests,
  startLiveKitAvatarClient,
} from '@/services/realtime/livekitAvatarClient';
import type { DisplayMessage } from '@/store/chat';

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));

const livekitEvents = {
  Connected: 'connected',
  Disconnected: 'disconnected',
  TrackSubscribed: 'trackSubscribed',
  TrackUnsubscribed: 'trackUnsubscribed',
};

let lastRoom: FakeLiveKitRoom | null = null;

class FakeMediaStream {
  constructor(public readonly tracks: MediaStreamTrack[] = []) {}

  getTracks(): MediaStreamTrack[] {
    return this.tracks;
  }
}

class FakeLiveKitRoom {
  handlers = new Map<string, (...args: unknown[]) => void>();
  textHandlers = new Map<string, (reader: AsyncIterable<string> & {
    info: { id: string; attributes: Record<string, unknown> };
  }, participantInfo: { identity: string }) => void>();
  connect = vi.fn(async () => undefined);
  disconnect = vi.fn();
  localParticipant = {
    setMicrophoneEnabled: vi.fn(async () => undefined),
  };

  constructor() {
    lastRoom = this;
  }

  on(event: string, callback: (...args: unknown[]) => void): FakeLiveKitRoom {
    this.handlers.set(event, callback);
    return this;
  }

  registerTextStreamHandler(
    topic: string,
    callback: (reader: AsyncIterable<string> & {
      info: { id: string; attributes: Record<string, unknown> };
    }, participantInfo: { identity: string }) => void,
  ): void {
    this.textHandlers.set(topic, callback);
  }

  unregisterTextStreamHandler(topic: string): void {
    this.textHandlers.delete(topic);
  }

  emit(event: string, ...args: unknown[]): void {
    this.handlers.get(event)?.(...args);
  }

  emitTextStream(
    topic: string,
    chunks: string[],
    participantIdentity: string,
    attributes: Record<string, unknown> = {},
  ): void {
    const reader = {
      info: { id: `${participantIdentity}-segment`, attributes },
      async *[Symbol.asyncIterator]() {
        for (const chunk of chunks) yield chunk;
      },
    };
    this.textHandlers.get(topic)?.(reader, { identity: participantIdentity });
  }

  emitAsyncTextStream(
    topic: string,
    chunks: AsyncIterable<string>,
    participantIdentity: string,
    attributes: Record<string, unknown> = {},
  ): void {
    const reader = {
      info: { id: `${participantIdentity}-segment`, attributes },
      [Symbol.asyncIterator]() {
        return chunks[Symbol.asyncIterator]();
      },
    };
    this.textHandlers.get(topic)?.(reader, { identity: participantIdentity });
  }
}

const fakeLiveKitModule = {
  Room: FakeLiveKitRoom,
  RoomEvent: livekitEvents,
  Track: {
    Kind: {
      Audio: 'audio',
      Video: 'video',
    },
  },
};

function livekitOptions(overrides: Partial<Parameters<typeof startLiveKitAvatarClient>[0]> = {}) {
  return {
    conversationId: 'conv_avatar',
    interfaceLanguage: 'zh-TW' as const,
    recentMessages: () => [],
    onRemoteStream: vi.fn(),
    onRemoteVideoStream: vi.fn(),
    onStatus: vi.fn(),
    onPlaybackState: vi.fn(),
    onAssistantResponseStarted: vi.fn(),
    onUserTranscript: vi.fn(),
    onAssistantTranscriptDelta: vi.fn(),
    onAssistantTranscriptDone: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

function message(role: 'user' | 'assistant', content: string): DisplayMessage {
  return {
    id: `${role}_${content}`,
    userId: 'user_1',
    conversationId: 'conv_avatar',
    role,
    content,
    createdAt: new Date('2026-09-07T00:00:00.000Z'),
  };
}

function mockAvatarSession(): void {
  vi.mocked(authenticatedFetch).mockResolvedValueOnce(
    new Response(JSON.stringify({
      livekit_url: 'wss://example.livekit.cloud',
      token: 'lk_join_token',
      room_name: 'areqa-live-room',
      participant_identity: 'learner-abc',
      agent_name: 'areqa-live-tutor',
      session_id: 'session-abc',
      expires_in: 120,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

describe('LiveKit avatar client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    lastRoom = null;
    vi.stubGlobal('MediaStream', FakeMediaStream);
    __setLiveKitClientLoaderForTests(async () => fakeLiveKitModule);
  });

  async function flushAsyncWork(cycles = 6): Promise<void> {
    for (let index = 0; index < cycles; index += 1) {
      await Promise.resolve();
    }
  }

  async function resolveAvatarVideoTrack(): Promise<void> {
    await vi.waitFor(() => {
      expect(lastRoom).not.toBeNull();
      expect(lastRoom?.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true);
    });
    lastRoom?.emit(
      livekitEvents.TrackSubscribed,
      { kind: 'video', mediaStreamTrack: {} as MediaStreamTrack },
      { kind: 'video' },
    );
  }

  it('fetches a LiveKit avatar session and publishes microphone audio after connect', async () => {
    mockAvatarSession();
    const options = livekitOptions();

    const clientPromise = startLiveKitAvatarClient(options);
    await resolveAvatarVideoTrack();
    const controller = await clientPromise;

    expect(authenticatedFetch).toHaveBeenCalledWith('/api/realtime/livekit-avatar-session', expect.objectContaining({
      method: 'POST',
    }));
    expect(JSON.parse(String(vi.mocked(authenticatedFetch).mock.calls[0]?.[1]?.body))).toEqual(expect.objectContaining({
      conversation_id: 'conv_avatar',
      interface_language: 'zh-TW',
      messages: [],
    }));
    expect(lastRoom?.connect).toHaveBeenCalledWith('wss://example.livekit.cloud', 'lk_join_token');
    expect(lastRoom?.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true);
    controller.setMuted(true);
    expect(lastRoom?.localParticipant.setMicrophoneEnabled).toHaveBeenLastCalledWith(false);
    controller.disconnect();
    expect(lastRoom?.disconnect).toHaveBeenCalled();
  });

  it('sends bounded recent message context when starting an avatar session', async () => {
    mockAvatarSession();
    const options = livekitOptions({
      recentMessages: () => [
        message('user', '請根據剛剛的討論繼續說明。'),
        message('assistant', '我們剛剛正在討論傅立葉轉換的直覺。'),
      ],
    });

    const clientPromise = startLiveKitAvatarClient(options);
    await resolveAvatarVideoTrack();
    await clientPromise;

    expect(JSON.parse(String(vi.mocked(authenticatedFetch).mock.calls[0]?.[1]?.body))).toEqual(expect.objectContaining({
      messages: [
        { role: 'user', content: '請根據剛剛的討論繼續說明。' },
        { role: 'assistant', content: '我們剛剛正在討論傅立葉轉換的直覺。' },
      ],
    }));
  });

  it('forwards subscribed LiveKit audio and video tracks to Live Tutor callbacks', async () => {
    mockAvatarSession();
    const options = livekitOptions();
    const clientPromise = startLiveKitAvatarClient(options);
    await vi.waitFor(() => {
      expect(lastRoom).not.toBeNull();
      expect(lastRoom?.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true);
    });

    const audioTrack = { kind: 'audio', mediaStreamTrack: {} as MediaStreamTrack };
    const videoTrack = { kind: 'video', mediaStreamTrack: {} as MediaStreamTrack };
    lastRoom?.emit(livekitEvents.Connected);
    lastRoom?.emit(livekitEvents.TrackSubscribed, audioTrack, { kind: 'audio' });
    lastRoom?.emit(livekitEvents.TrackSubscribed, videoTrack, { kind: 'video' });
    await clientPromise;

    expect(options.onStatus).toHaveBeenCalledWith('listening');
    expect(options.onRemoteStream).toHaveBeenCalledWith(expect.any(MediaStream));
    expect(options.onPlaybackState).toHaveBeenCalledWith('started');
    expect(options.onRemoteVideoStream).toHaveBeenCalledWith(expect.any(MediaStream));
  });

  it('reports runtime disconnects as errors so the panel can fall back to direct voice', async () => {
    mockAvatarSession();
    const options = livekitOptions();
    const clientPromise = startLiveKitAvatarClient(options);
    await resolveAvatarVideoTrack();
    const controller = await clientPromise;

    lastRoom?.emit(livekitEvents.Disconnected);

    expect(options.onRemoteVideoStream).toHaveBeenCalledWith(null);
    expect(options.onPlaybackState).toHaveBeenCalledWith('interrupted');
    expect(options.onStatus).toHaveBeenCalledWith('error');
    expect(options.onError).toHaveBeenCalledWith(expect.objectContaining({
      message: 'LiveKit avatar room disconnected',
    }));
    controller.disconnect();
  });

  it('clears avatar video when the LiveKit video track is unsubscribed', async () => {
    mockAvatarSession();
    const options = livekitOptions();
    const clientPromise = startLiveKitAvatarClient(options);
    await resolveAvatarVideoTrack();
    const controller = await clientPromise;

    lastRoom?.emit(livekitEvents.TrackUnsubscribed, { kind: 'video' }, { kind: 'video' });

    expect(options.onRemoteVideoStream).toHaveBeenCalledWith(null);
    controller.disconnect();
  });

  it('forwards LiveKit transcription text streams through realtime callbacks', async () => {
    vi.useFakeTimers();
    mockAvatarSession();
    const options = livekitOptions();
    const clientPromise = startLiveKitAvatarClient(options);
    await vi.waitFor(() => {
      expect(lastRoom).not.toBeNull();
      expect(lastRoom?.textHandlers.has('lk.transcription')).toBe(true);
    });

    lastRoom?.emitTextStream('lk.transcription', ['你好，我想練習口說'], 'learner-abc', {
      'lk.transcription_final': 'true',
    });
    lastRoom?.emitTextStream('lk.transcription', ['可以，', '我們開始。'], 'areqa-live-tutor', {
      'lk.transcription_final': 'true',
    });
    await flushAsyncWork();
    await resolveAvatarVideoTrack();
    await clientPromise;
    await vi.advanceTimersByTimeAsync(900);

    expect(options.onUserTranscript).toHaveBeenCalledWith('你好，我想練習口說', 'learner-abc-segment');
    expect(options.onAssistantResponseStarted).toHaveBeenCalledOnce();
    expect(options.onAssistantTranscriptDelta).toHaveBeenNthCalledWith(1, '可以，');
    expect(options.onAssistantTranscriptDelta).toHaveBeenNthCalledWith(2, '我們開始。');
    expect(options.onAssistantTranscriptDone).toHaveBeenCalledWith('可以，我們開始。');
  });

  it('merges adjacent assistant transcription streams before finalizing the visible reply', async () => {
    vi.useFakeTimers();
    mockAvatarSession();
    const options = livekitOptions();
    const clientPromise = startLiveKitAvatarClient(options);
    await vi.waitFor(() => {
      expect(lastRoom).not.toBeNull();
      expect(lastRoom?.textHandlers.has('lk.transcription')).toBe(true);
    });

    lastRoom?.emitTextStream('lk.transcription', ['好的，我先簡單說明。'], 'areqa-live-tutor', {
      'lk.transcription_final': 'true',
    });
    await flushAsyncWork();
    await vi.advanceTimersByTimeAsync(450);
    lastRoom?.emitTextStream('lk.transcription', ['這篇論文是在討論 ICAP。'], 'areqa-live-tutor', {
      'lk.transcription_final': 'true',
    });
    await flushAsyncWork();
    await resolveAvatarVideoTrack();
    await clientPromise;

    expect(options.onAssistantResponseStarted).toHaveBeenCalledOnce();
    expect(options.onAssistantTranscriptDelta).toHaveBeenNthCalledWith(1, '好的，我先簡單說明。');
    expect(options.onAssistantTranscriptDelta).toHaveBeenNthCalledWith(2, '這篇論文是在討論 ICAP。');
    expect(options.onAssistantTranscriptDone).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(900);

    expect(options.onAssistantTranscriptDone).toHaveBeenCalledOnce();
    expect(options.onAssistantTranscriptDone).toHaveBeenCalledWith('好的，我先簡單說明。這篇論文是在討論 ICAP。');
  });

  it('drops stale assistant transcription after canceling speech and accepts the next assistant stream', async () => {
    vi.useFakeTimers();
    mockAvatarSession();
    let releaseOldStream: (() => void) | null = null;
    const options = livekitOptions();
    const clientPromise = startLiveKitAvatarClient(options);
    await vi.waitFor(() => {
      expect(lastRoom).not.toBeNull();
      expect(lastRoom?.textHandlers.has('lk.transcription')).toBe(true);
    });

    lastRoom?.emitAsyncTextStream('lk.transcription', (async function* oldAssistantStream() {
      yield '舊回答第一段';
      await new Promise<void>((resolve) => {
        releaseOldStream = resolve;
      });
      yield '舊回答第二段';
    })(), 'areqa-live-tutor', {
      'lk.transcription_final': 'true',
    });
    await flushAsyncWork();

    const controller = await (async () => {
      await resolveAvatarVideoTrack();
      return clientPromise;
    })();
    expect(options.onAssistantTranscriptDelta).toHaveBeenCalledWith('舊回答第一段');

    controller.cancelSpeech();
    releaseOldStream?.();
    await flushAsyncWork();
    await vi.advanceTimersByTimeAsync(900);

    lastRoom?.emitTextStream('lk.transcription', ['新回答'], 'areqa-live-tutor', {
      'lk.transcription_final': 'true',
    });
    await flushAsyncWork();
    await vi.advanceTimersByTimeAsync(900);

    expect(options.onPlaybackState).toHaveBeenCalledWith('interrupted');
    expect(options.onAssistantTranscriptDelta).not.toHaveBeenCalledWith('舊回答第二段');
    expect(options.onAssistantTranscriptDone).toHaveBeenCalledTimes(1);
    expect(options.onAssistantTranscriptDone).toHaveBeenCalledWith('新回答');
    controller.disconnect();
  });

  it('reports setup errors through the existing Live Tutor error boundary', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('missing config', { status: 503 }));
    const onError = vi.fn();

    const controller = await startLiveKitAvatarClient(livekitOptions({ onError }));

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    controller.disconnect();
  });

  it('reports a setup error when no avatar video track arrives before timeout', async () => {
    vi.useFakeTimers();
    mockAvatarSession();
    const onError = vi.fn();
    const clientPromise = startLiveKitAvatarClient(livekitOptions({ onError }));
    await flushAsyncWork();

    await vi.advanceTimersByTimeAsync(44_999);
    expect(onError).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    const controller = await clientPromise;

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      message: expect.stringContaining('LiveKit avatar video track was not received'),
    }));
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      message: expect.stringContaining('room=areqa-live-room, agent=areqa-live-tutor'),
    }));
    expect(lastRoom?.disconnect).toHaveBeenCalled();
    controller.disconnect();
  });
});
