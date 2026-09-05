import React from 'react';
import { act, render, screen, waitFor, type RenderResult } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveTutorPanel } from '@/components/LiveTutor/LiveTutorPanel';
import { playLiveVoiceCue, startRealtimeClient, type StartRealtimeClientOptions } from '@/services/realtime';
import { cancelCurrentStream } from '@/services/chat';
import { useChatStore, type DisplayMessage } from '@/store/chat';
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
  cancelCurrentStream: vi.fn(),
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

const controller = {
  setMuted: vi.fn(),
  cancelSpeech: vi.fn(),
  disconnect: vi.fn(),
};

let realtimeOptions: StartRealtimeClientOptions | null = null;

function message(role: 'user' | 'assistant', content: string, conversationId = 'conv_paper'): DisplayMessage {
  return {
    id: `${role}-${content}`,
    userId: 'user_1',
    conversationId,
    role,
    content,
    createdAt: new Date('2026-09-05T00:00:00.000Z'),
  };
}

function resetStores(): void {
  useLiveTutorStore.setState({
    isOpen: false,
    status: 'idle',
    isMuted: false,
    closeRequestId: 0,
    userTranscript: '',
    assistantTranscript: '',
    error: null,
  });
  useConversationStore.setState({
    activeConversationId: 'conv_paper',
    conversations: [],
    isLoading: false,
    isMessageHandoffLoading: false,
    error: null,
    streamingTitles: {},
  });
  useChatStore.setState({
    messages: [message('user', '這篇論文的背景內容')],
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

async function renderOpenPanel(
  props: { activeConversationId?: string | null; hasMessages?: boolean } = {},
): Promise<RenderResult> {
  act(() => {
    useLiveTutorStore.getState().open();
  });
  let result: RenderResult | null = null;
  await act(async () => {
    result = render(
      <LiveTutorPanel
        activeConversationId={props.activeConversationId ?? 'conv_paper'}
        hasMessages={props.hasMessages ?? true}
      />,
    );
  });
  return result;
}

describe('LiveTutorPanel realtime-primary voice integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    realtimeOptions = null;
    resetStores();
    vi.mocked(startRealtimeClient).mockImplementation(async (options) => {
      realtimeOptions = options;
      options.onStatus('listening');
      return controller;
    });
    vi.mocked(cancelCurrentStream).mockResolvedValue(undefined);
  });

  afterEach(() => {
    resetStores();
  });

  it('mirrors realtime user and assistant transcripts into the chat without AREQA stream', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('请解释这篇论文');
    });
    act(() => {
      realtimeOptions?.onAssistantResponseStarted?.();
      realtimeOptions?.onAssistantTranscriptDelta('可以，我先簡短說。');
      realtimeOptions?.onAssistantTranscriptDone('可以，我先簡短說。');
    });

    await waitFor(() => {
      const messages = useChatStore.getState().messages;
      expect(messages).toEqual(expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '請解釋這篇論文' }),
        expect.objectContaining({ role: 'assistant', content: '可以，我先簡短說。', isStreaming: false }),
      ]));
    });
    expect(realtimeOptions?.conversationId).toBe('conv_paper');
    act(() => view.unmount());
  });

  it('shows only Connecting before the realtime channel is ready', async () => {
    vi.mocked(startRealtimeClient).mockImplementation(async (options) => {
      realtimeOptions = options;
      options.onStatus('connecting');
      return controller;
    });

    const view = await renderOpenPanel();

    expect(screen.getByText('Connecting')).toBeInTheDocument();
    act(() => view.unmount());
  });

  it('ignores speech transcripts before the realtime session is listening', async () => {
    vi.mocked(startRealtimeClient).mockImplementation(async (options) => {
      realtimeOptions = options;
      options.onStatus('connecting');
      return controller;
    });
    const view = await renderOpenPanel();

    await act(async () => {
      realtimeOptions?.onUserTranscript('你好');
    });

    expect(useChatStore.getState().messages).toHaveLength(1);
    act(() => view.unmount());
  });

  it('plays lifecycle cues for connected, mute, unmute, and hangup states', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    expect(playLiveVoiceCue).toHaveBeenCalledWith('connected');

    act(() => {
      useLiveTutorStore.getState().setMuted(true);
    });
    expect(playLiveVoiceCue).toHaveBeenCalledWith('muted');

    act(() => {
      useLiveTutorStore.getState().setMuted(false);
    });
    expect(playLiveVoiceCue).toHaveBeenCalledWith('unmuted');

    act(() => {
      useLiveTutorStore.getState().requestClose();
    });
    await waitFor(() => expect(playLiveVoiceCue).toHaveBeenCalledWith('hangup'));
    act(() => view.unmount());
  });

  it('keeps the realtime session alive when the first voice turn creates a conversation', async () => {
    useConversationStore.setState({ activeConversationId: null });
    useChatStore.setState({ messages: [] });

    const view = await renderOpenPanel({ activeConversationId: null, hasMessages: false });
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      useConversationStore.setState({ activeConversationId: 'conv_created' });
      view.rerender(<LiveTutorPanel activeConversationId="conv_created" hasMessages />);
    });

    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());
    expect(controller.disconnect).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('shows Lost Connection when realtime setup fails', async () => {
    vi.mocked(startRealtimeClient).mockImplementation(async (options) => {
      realtimeOptions = options;
      options.onError(new Error('provider down'));
      return controller;
    });

    const view = await renderOpenPanel();

    await waitFor(() => expect(screen.getByText('Lost Connection')).toBeInTheDocument());
    act(() => view.unmount());
  });

  it('streams visible assistant text from realtime speech transcript deltas', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onAssistantResponseStarted?.();
      realtimeOptions?.onAssistantTranscriptDelta('AREQA 根據');
      realtimeOptions?.onAssistantTranscriptDelta('目前對話脈絡');
    });

    await waitFor(() => {
      expect(useChatStore.getState().messages.at(-1)).toEqual(expect.objectContaining({
        role: 'assistant',
        content: 'AREQA 根據目前對話脈絡',
        isStreaming: true,
      }));
    });

    act(() => {
      realtimeOptions?.onAssistantTranscriptDone('AREQA 根據目前對話脈絡');
    });

    await waitFor(() => {
      expect(useChatStore.getState().messages.at(-1)).toEqual(expect.objectContaining({
        role: 'assistant',
        content: 'AREQA 根據目前對話脈絡',
        isStreaming: false,
      }));
    });
    act(() => view.unmount());
  });

  it('cancels stale text streaming and realtime speech when a new voice turn starts', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onUserSpeechStarted?.();
    });

    expect(controller.cancelSpeech).toHaveBeenCalledOnce();
    expect(cancelCurrentStream).toHaveBeenCalledOnce();
    act(() => view.unmount());
  });

  it('cancels text streaming and realtime speech when voice mode closes', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      useLiveTutorStore.getState().requestClose();
    });

    await waitFor(() => {
      expect(controller.cancelSpeech).toHaveBeenCalled();
      expect(controller.disconnect).toHaveBeenCalled();
      expect(cancelCurrentStream).toHaveBeenCalled();
    });
    act(() => view.unmount());
  });
});
