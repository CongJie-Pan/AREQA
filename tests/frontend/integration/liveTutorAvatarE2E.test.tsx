import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatInput } from '@/components/ChatInput';
import { LiveTutorPanel } from '@/components/LiveTutor/LiveTutorPanel';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import {
  __setLiveKitClientLoaderForTests,
  type StartRealtimeClientOptions,
} from '@/services/realtime';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useLiveTutorStore } from '@/store/liveTutor';

const startRealtimeClientMock = vi.hoisted(() => vi.fn());
const playLiveVoiceCueMock = vi.hoisted(() => vi.fn());

vi.mock('next/image', () => ({
  default: ({ alt, ...props }: { alt: string; src: string }) => <img alt={alt} {...props} />,
}));

vi.mock('@/services/realtime', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/realtime')>();
  return {
    ...actual,
    RealtimeClientError: class RealtimeClientError extends Error {
      constructor(public readonly code: string, message: string) {
        super(message);
      }
    },
    playLiveVoiceCue: playLiveVoiceCueMock,
    startRealtimeClient: startRealtimeClientMock,
  };
});

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  cancelCurrentStream: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/database/db', () => ({
  getCurrentUserId: vi.fn(() => null),
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    message: {
      add: vi.fn(),
    },
  },
}));

const livekitEvents = {
  Connected: 'connected',
  Disconnected: 'disconnected',
  TrackSubscribed: 'trackSubscribed',
  TrackUnsubscribed: 'trackUnsubscribed',
};

class FakeMediaStream {
  constructor(private readonly tracks: MediaStreamTrack[] = []) {}

  getTracks(): MediaStreamTrack[] {
    return this.tracks;
  }

  getVideoTracks(): MediaStreamTrack[] {
    return this.tracks.filter((track) => track.kind === 'video');
  }

  getAudioTracks(): MediaStreamTrack[] {
    return this.tracks.filter((track) => track.kind === 'audio');
  }
}

class FakeLiveKitRoom {
  handlers = new Map<string, (...args: unknown[]) => void>();
  connect = vi.fn(async () => {
    this.handlers.get(livekitEvents.Connected)?.();
  });
  disconnect = vi.fn();
  localParticipant = {
    setMicrophoneEnabled: vi.fn(async () => undefined),
  };

  constructor() {
    fakeRooms.push(this);
  }

  on(event: string, callback: (...args: unknown[]) => void): FakeLiveKitRoom {
    this.handlers.set(event, callback);
    return this;
  }

  registerTextStreamHandler(): void {
    return undefined;
  }

  unregisterTextStreamHandler(): void {
    return undefined;
  }

  emitVideoTrack(): void {
    this.handlers.get(livekitEvents.TrackSubscribed)?.(
      { kind: 'video', mediaStreamTrack: { kind: 'video' } as MediaStreamTrack },
      { kind: 'video' },
    );
  }
}

const fakeRooms: FakeLiveKitRoom[] = [];
const stableRoomName = 'areqa-live-443de5aa21020628';

function resetLiveTutorHarness(): void {
  useLiveTutorStore.setState({
    isOpen: false,
    status: 'idle',
    isMuted: false,
    avatarEnabled: false,
    closeRequestId: 0,
    userTranscript: '',
    assistantTranscript: '',
    error: null,
  });
  useConversationStore.setState({
    activeConversationId: 'conv_avatar',
    conversations: [],
    isLoading: false,
    isMessageHandoffLoading: false,
    error: null,
    streamingTitles: {},
  });
  useChatStore.setState({
    messages: [],
    isStreaming: false,
    currentStreamingId: null,
    thinkingContent: '',
    thinkingStartTime: null,
    isThinking: false,
    currentContent: '',
    currentCitations: [],
    currentAnswerBlocks: [],
    quotedText: null,
    error: null,
    tokenUsage: null,
    ragStatus: 'idle',
    ragMessage: '',
    ragSources: [],
  });
}

function LiveTutorAvatarHarness() {
  const isLiveVoiceActive = useLiveTutorStore((state) => state.isOpen);
  const isLiveVoiceMuted = useLiveTutorStore((state) => state.isMuted);
  const isLiveVoiceAvatarEnabled = useLiveTutorStore((state) => state.avatarEnabled);
  const openLiveTutor = useLiveTutorStore((state) => state.open);
  const setLiveTutorMuted = useLiveTutorStore((state) => state.setMuted);
  const setLiveTutorAvatarEnabled = useLiveTutorStore((state) => state.setAvatarEnabled);
  const requestCloseLiveTutor = useLiveTutorStore((state) => state.requestClose);

  return (
    <>
      <LiveTutorPanel activeConversationId="conv_avatar" hasMessages={false} />
      <ChatInput
        onSend={vi.fn()}
        onOpenLiveTutor={openLiveTutor}
        isLiveVoiceActive={isLiveVoiceActive}
        isLiveVoiceMuted={isLiveVoiceMuted}
        isLiveVoiceAvatarEnabled={isLiveVoiceAvatarEnabled}
        onToggleLiveVoiceMute={() => setLiveTutorMuted(!useLiveTutorStore.getState().isMuted)}
        onToggleLiveVoiceAvatar={() => setLiveTutorAvatarEnabled(!useLiveTutorStore.getState().avatarEnabled)}
        onCloseLiveVoice={requestCloseLiveTutor}
      />
    </>
  );
}

function liveKitAvatarResponse(): Response {
  return new Response(JSON.stringify({
    livekit_url: 'wss://example.livekit.cloud',
    token: 'lk_join_token',
    room_name: stableRoomName,
    participant_identity: 'learner-stable',
    agent_name: 'areqa-live-tutor',
    expires_in: 900,
  }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('Live Tutor avatar E2E integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    fakeRooms.length = 0;
    resetLiveTutorHarness();
    vi.stubGlobal('MediaStream', FakeMediaStream);
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    __setLiveKitClientLoaderForTests(async () => ({
      Room: FakeLiveKitRoom,
      RoomEvent: livekitEvents,
      Track: {
        Kind: {
          Audio: 'audio',
          Video: 'video',
        },
      },
    }));
    startRealtimeClientMock.mockImplementation(async (options: StartRealtimeClientOptions) => {
      options.onStatus('listening');
      return {
        setMuted: vi.fn(),
        cancelSpeech: vi.fn(),
        speakText: vi.fn(() => true),
        disconnect: vi.fn(),
      };
    });
    vi.mocked(authenticatedFetch).mockImplementation(async () => liveKitAvatarResponse());
  });

  it('renders avatar video through the real LiveKit client path without creating a second room', async () => {
    const { container, unmount } = render(<LiveTutorAvatarHarness />);

    fireEvent.click(screen.getByLabelText('開啟即時語音'));
    await waitFor(() => expect(startRealtimeClientMock).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByLabelText('開啟虛擬角色'));
    await waitFor(() => expect(authenticatedFetch).toHaveBeenCalledOnce());
    await waitFor(() => expect(fakeRooms[0]?.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true));

    expect(startRealtimeClientMock).toHaveBeenCalledOnce();
    expect(fakeRooms).toHaveLength(1);
    expect(container.querySelector('[data-avatar-state="fallback"]')).not.toBeInTheDocument();
    expect(screen.getByText('Connecting')).toBeInTheDocument();

    await act(async () => {
      fakeRooms[0]?.emitVideoTrack();
    });

    await waitFor(() => expect(document.querySelector('video')).toBeInTheDocument());
    expect(container.querySelector('[data-avatar-window="floating"]')).toBeInTheDocument();
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/realtime/livekit-avatar-session', expect.objectContaining({
      method: 'POST',
    }));
    expect(JSON.parse(String(vi.mocked(authenticatedFetch).mock.calls[0]?.[1]?.body))).toEqual(expect.objectContaining({
      conversation_id: 'conv_avatar',
      interface_language: 'zh-TW',
    }));
    expect(fakeRooms[0]?.connect).toHaveBeenCalledWith('wss://example.livekit.cloud', 'lk_join_token');

    unmount();
  });
});
