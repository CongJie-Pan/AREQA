import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatInput } from '@/components/ChatInput';
import { LiveTutorPanel } from '@/components/LiveTutor/LiveTutorPanel';
import { startRealtimeClient, type StartRealtimeClientOptions } from '@/services/realtime';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useLiveTutorStore } from '@/store/liveTutor';

vi.mock('next/image', () => ({
  default: ({ alt, ...props }: { alt: string; src: string }) => <img alt={alt} {...props} />,
}));

vi.mock('@/services/realtime', () => ({
  RealtimeClientError: class RealtimeClientError extends Error {
    constructor(public readonly code: string, message: string) {
      super(message);
    }
  },
  playLiveVoiceCue: vi.fn(),
  startRealtimeClient: vi.fn(),
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

let realtimeOptions: StartRealtimeClientOptions | null = null;

function avatarStream(): MediaStream {
  return {
    getVideoTracks: () => [{ readyState: 'live' }],
    getAudioTracks: () => [],
    getTracks: () => [],
  } as unknown as MediaStream;
}

function resetLiveTutorHarness(): void {
  useLiveTutorStore.setState({
    isOpen: false,
    status: 'idle',
    isMuted: false,
    avatarEnabled: true,
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

describe('Live Tutor avatar flow integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    realtimeOptions = null;
    resetLiveTutorHarness();
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.mocked(startRealtimeClient).mockImplementation(async (options) => {
      realtimeOptions = options;
      options.onStatus('listening');
      return {
        setMuted: vi.fn(),
        cancelSpeech: vi.fn(),
        disconnect: vi.fn(),
      };
    });
  });

  it('lets the composer avatar button switch the live tutor stage between video and logo fallback', async () => {
    const { container } = render(<LiveTutorAvatarHarness />);

    fireEvent.click(screen.getByLabelText('開啟即時語音'));
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onRemoteVideoStream?.(avatarStream());
    });
    expect(document.querySelector('video')).toBeInTheDocument();
    expect(screen.getByLabelText('關閉虛擬角色')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('關閉虛擬角色'));

    expect(document.querySelector('video')).not.toBeInTheDocument();
    expect(container.querySelector('img')).toHaveAttribute('src', '/icon/areqa_icon_v4_circle.png');
    expect(screen.getByLabelText('開啟虛擬角色')).toBeInTheDocument();
  });
});
