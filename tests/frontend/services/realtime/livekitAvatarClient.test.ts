import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import {
  __setLiveKitClientLoaderForTests,
  startLiveKitAvatarClient,
} from '@/services/realtime/livekitAvatarClient';

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

  emit(event: string, ...args: unknown[]): void {
    this.handlers.get(event)?.(...args);
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
    onUserTranscript: vi.fn(),
    onAssistantTranscriptDelta: vi.fn(),
    onAssistantTranscriptDone: vi.fn(),
    onError: vi.fn(),
    ...overrides,
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
    expect(lastRoom?.connect).toHaveBeenCalledWith('wss://example.livekit.cloud', 'lk_join_token');
    expect(lastRoom?.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true);
    controller.setMuted(true);
    expect(lastRoom?.localParticipant.setMicrophoneEnabled).toHaveBeenLastCalledWith(false);
    controller.disconnect();
    expect(lastRoom?.disconnect).toHaveBeenCalled();
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

    await vi.advanceTimersByTimeAsync(15_000);
    const controller = await clientPromise;

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      message: expect.stringContaining('LiveKit avatar video track was not received'),
    }));
    expect(lastRoom?.disconnect).toHaveBeenCalled();
    controller.disconnect();
  });
});
