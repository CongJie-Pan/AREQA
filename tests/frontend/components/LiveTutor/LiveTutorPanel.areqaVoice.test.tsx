import React from 'react';
import { act, render, screen, waitFor, type RenderResult } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveTutorPanel } from '@/components/LiveTutor/LiveTutorPanel';
import {
  playLiveVoiceCue,
  RealtimeClientError,
  startLiveKitAvatarClient,
  startRealtimeClient,
  type StartRealtimeClientOptions,
} from '@/services/realtime';
import { cancelCurrentStream, sendMessage } from '@/services/chat';
import { useChatStore, type DisplayMessage } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useLiveTutorStore } from '@/store/liveTutor';
import { getCurrentUserId } from '@/database/db';
import { databaseService } from '@/services/database';
import { loadVoiceMaterial, prepareVoiceAttachments } from '@/services/realtime/attachments';
import { generateConversationImage } from '@/services/generatedImages';

vi.mock('next/image', () => ({
  default: ({ alt, ...props }: { alt: string; src: string }) => <img alt={alt} {...props} />,
}));

vi.mock('@/services/realtime', () => ({
  RealtimeClientError: class RealtimeClientError extends Error {
    constructor(public readonly code: string, message: string, public readonly recoverable = false) {
      super(message);
    }
  },
  playLiveVoiceCue: vi.fn(),
  startLiveKitAvatarClient: vi.fn(),
  startRealtimeClient: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  cancelCurrentStream: vi.fn(),
  sendMessage: vi.fn(),
}));

vi.mock('@/services/realtime/attachments', () => ({
  loadVoiceMaterial: vi.fn(),
  prepareVoiceAttachments: vi.fn(),
}));

vi.mock('@/services/generatedImages', () => ({
  generateConversationImage: vi.fn(),
}));

vi.mock('@/database/db', () => ({
  getCurrentUserId: vi.fn(() => null),
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      create: vi.fn(),
    },
    message: {
      add: vi.fn(),
    },
  },
}));

const controller = {
  setMuted: vi.fn(),
  cancelSpeech: vi.fn(),
  speakText: vi.fn(() => true),
  requestResponse: vi.fn(),
  addAttachmentContext: vi.fn(async () => true),
  sendUserText: vi.fn(async () => true),
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
    avatarEnabled: false,
    closeRequestId: 0,
    userTranscript: '',
    assistantTranscript: '',
    error: null,
    sendVoiceMessage: null,
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
    tutorProfile: 'general',
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
  props: { activeConversationId?: string | null; hasMessages?: boolean; layout?: 'inline' | 'side-pane' } = {},
): Promise<RenderResult> {
  act(() => {
    useLiveTutorStore.getState().open();
  });
  let result: RenderResult | null = null;
  await act(async () => {
    result = render(
      <LiveTutorPanel
        activeConversationId={props.activeConversationId === undefined ? 'conv_paper' : props.activeConversationId}
        hasMessages={props.hasMessages ?? true}
        layout={props.layout}
      />,
    );
  });
  return result;
}

describe('LiveTutorPanel realtime-primary voice integration', () => {
  const originalGenerateTitle = useConversationStore.getState().generateTitle;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue(null);
    controller.speakText.mockReturnValue(true);
    controller.addAttachmentContext.mockResolvedValue(true);
    controller.sendUserText.mockResolvedValue(true);
    vi.mocked(loadVoiceMaterial).mockResolvedValue(null);
    vi.mocked(generateConversationImage).mockResolvedValue({ completed: false });
    vi.mocked(databaseService.message.add).mockResolvedValue(undefined as never);
    realtimeOptions = null;
    resetStores();
    vi.mocked(startRealtimeClient).mockImplementation(async (options) => {
      realtimeOptions = options;
      options.onStatus('listening');
      return controller;
    });
    vi.mocked(startLiveKitAvatarClient).mockImplementation(async (options) => {
      realtimeOptions = options;
      options.onStatus('listening');
      return controller;
    });
    vi.mocked(cancelCurrentStream).mockResolvedValue(undefined);
    vi.mocked(sendMessage).mockResolvedValue({ completed: true });
  });

  afterEach(() => {
    resetStores();
    useConversationStore.setState({ generateTitle: originalGenerateTitle });
  });

  it('titles a new voice conversation from its first finalized user transcript', async () => {
    vi.mocked(getCurrentUserId).mockReturnValue('user_1');
    const generateTitle = vi.fn().mockResolvedValue(undefined);
    useConversationStore.setState({ activeConversationId: null, conversations: [], generateTitle });
    useChatStore.setState({ messages: [] });
    vi.mocked(databaseService.conversation.create).mockResolvedValue({
      id: 'new-voice-conv', userId: 'user_1', title: '新對話',
      createdAt: new Date(), updatedAt: new Date(), messageCount: 0, lastMessagePreview: '',
    });

    const view = await renderOpenPanel({ activeConversationId: null, hasMessages: false });
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());
    expect(databaseService.conversation.create).not.toHaveBeenCalled();
    expect(generateTitle).not.toHaveBeenCalled();

    await act(async () => realtimeOptions?.onUserTranscript('請解釋光合作用', 'first-turn'));
    await waitFor(() => expect(generateTitle).toHaveBeenCalledWith('new-voice-conv', [
      { role: 'user', content: '請解釋光合作用' },
    ]));
    expect(databaseService.conversation.create).toHaveBeenCalledOnce();

    await act(async () => realtimeOptions?.onUserTranscript('再說明葉綠體', 'second-turn'));
    await waitFor(() => expect(useChatStore.getState().messages.some((item) => item.content === '再說明葉綠體')).toBe(true));
    expect(generateTitle).toHaveBeenCalledOnce();
    act(() => view.unmount());
  });

  it('titles an empty selected conversation from typed voice-mode text', async () => {
    vi.mocked(getCurrentUserId).mockReturnValue('user_1');
    const generateTitle = vi.fn().mockResolvedValue(undefined);
    useConversationStore.setState({
      generateTitle,
      conversations: [{ id: 'conv_paper', userId: 'user_1', title: '新對話',
        createdAt: new Date(), updatedAt: new Date(), messageCount: 0, lastMessagePreview: '' }],
    });
    useChatStore.setState({ messages: [] });
    const view = await renderOpenPanel({ hasMessages: false });
    await act(async () => {
      await useLiveTutorStore.getState().sendVoiceMessage?.('請介紹量子電腦', []);
    });
    expect(generateTitle).toHaveBeenCalledWith('conv_paper', [
      { role: 'user', content: '請介紹量子電腦' },
    ]);
    expect(generateTitle).toHaveBeenCalledOnce();
    act(() => view.unmount());
  });

  it('keeps an existing conversation title when voice mode receives a new turn', async () => {
    vi.mocked(getCurrentUserId).mockReturnValue('user_1');
    const generateTitle = vi.fn().mockResolvedValue(undefined);
    useConversationStore.setState({
      generateTitle,
      conversations: [{ id: 'conv_paper', userId: 'user_1', title: '既有標題',
        createdAt: new Date(), updatedAt: new Date(), messageCount: 0, lastMessagePreview: '' }],
    });
    useChatStore.setState({ messages: [] });
    const view = await renderOpenPanel({ hasMessages: false });

    await act(async () => realtimeOptions?.onUserTranscript('繼續說明', 'existing-turn'));
    await waitFor(() => expect(useChatStore.getState().messages.some((item) => item.content === '繼續說明')).toBe(true));
    expect(generateTitle).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('passes the selected English Tutor profile to voice sessions', async () => {
    useChatStore.getState().setTutorProfile('english');
    const view = await renderOpenPanel();

    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());
    expect(vi.mocked(startRealtimeClient).mock.calls[0]?.[0].tutorProfile).toBe('english');
    act(() => view.unmount());
  });

  it('creates a voice-requested teaching image without blocking the voice turn', async () => {
    vi.mocked(getCurrentUserId).mockReturnValue('user_1');
    vi.mocked(generateConversationImage).mockResolvedValue({
      completed: true,
      block: { type: 'image_block', slotId: 'image-1', topic: 'cycle', purpose: 'diagram',
        imageUrl: 'https://example.test/image.png', sourceUrl: '', sourceDomain: '', caption: 'cycle',
        safetyStatus: 'pass', matchConfidence: 1, visionSummary: 'The arrows form a cycle.' },
    });
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('請畫出水循環流程圖', 'image-turn-1');
    });
    await waitFor(() => expect(generateConversationImage).toHaveBeenCalledWith(
      '請畫出水循環流程圖', 'conv_paper', expect.any(String), false,
    ));
    await waitFor(() => expect(controller.speakText).toHaveBeenCalledWith(expect.stringContaining('The arrows form a cycle.')));
    expect(sendMessage).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('speaks an image explanation after the current voice reply finishes', async () => {
    vi.mocked(getCurrentUserId).mockReturnValue('user_1');
    let finishImage!: (result: Awaited<ReturnType<typeof generateConversationImage>>) => void;
    vi.mocked(generateConversationImage).mockImplementation(() => new Promise((resolve) => { finishImage = resolve; }));
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => realtimeOptions?.onUserTranscript('請畫出水循環流程圖', 'image-busy'));
    await waitFor(() => expect(generateConversationImage).toHaveBeenCalledOnce());
    await act(async () => {
      realtimeOptions?.onStatus('speaking');
      finishImage({ completed: true, block: {
        type: 'image_block', slotId: 'image-1', topic: 'cycle', purpose: 'diagram',
        imageUrl: 'https://example.test/image.png', sourceUrl: '', sourceDomain: '', caption: 'cycle',
        safetyStatus: 'pass', matchConfidence: 1, visionSummary: 'The arrows form a cycle.',
      } });
    });
    expect(controller.speakText).not.toHaveBeenCalled();
    await act(async () => realtimeOptions?.onPlaybackState('stopped'));
    await waitFor(() => expect(controller.speakText).toHaveBeenCalledWith(expect.stringContaining('The arrows form a cycle.')));
    act(() => view.unmount());
  });

  it('prepares and delivers an attachment while the voice session stays connected', async () => {
    vi.mocked(prepareVoiceAttachments).mockResolvedValue({
      conversation_id: 'conv_paper',
      version: 'version-1',
      material: { title: 'notes.txt', text: 'The unique finding is cobalt.', truncated: false },
    });
    const view = await renderOpenPanel();
    await waitFor(() => expect(useLiveTutorStore.getState().sendVoiceMessage).not.toBeNull());
    const file = new File(['The unique finding is cobalt.'], 'notes.txt', { type: 'text/plain' });

    await act(async () => {
      await useLiveTutorStore.getState().sendVoiceMessage?.('請分析檔案', [file]);
    });

    expect(prepareVoiceAttachments).toHaveBeenCalledWith('conv_paper', [file]);
    expect(controller.addAttachmentContext).toHaveBeenCalledWith(
      { title: 'notes.txt', text: 'The unique finding is cobalt.', truncated: false }, '請分析檔案',
    );
    expect(controller.requestResponse).toHaveBeenCalled();
    expect(useChatStore.getState().messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ role: 'user', content: '請分析檔案', attachments: expect.any(Array) }),
    ]));
    expect(controller.disconnect).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('sends typed text through the open voice session without starting a chat stream', async () => {
    const view = await renderOpenPanel();

    await act(async () => {
      await useLiveTutorStore.getState().sendVoiceMessage?.('請繼續說明', []);
    });

    expect(controller.sendUserText).toHaveBeenCalledWith('請繼續說明');
    expect(sendMessage).not.toHaveBeenCalled();
    expect(prepareVoiceAttachments).not.toHaveBeenCalled();
    expect(useChatStore.getState().messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ role: 'user', content: '請繼續說明' }),
    ]));
    act(() => view.unmount());
  });

  it('restores saved file content into a reopened voice session without speaking first', async () => {
    vi.mocked(loadVoiceMaterial).mockResolvedValue({
      title: 'notes.txt', text: 'The unique finding is cobalt.', truncated: false,
    });
    const view = await renderOpenPanel();

    await waitFor(() => expect(controller.addAttachmentContext).toHaveBeenCalledWith({
      title: 'notes.txt', text: 'The unique finding is cobalt.', truncated: false,
    }));
    expect(controller.requestResponse).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('keeps the upload draft recoverable when attachment delivery fails', async () => {
    vi.mocked(prepareVoiceAttachments).mockResolvedValue({
      conversation_id: 'conv_paper', version: 'version-1',
      material: { title: 'notes.txt', text: 'content', truncated: false },
    });
    controller.addAttachmentContext.mockResolvedValueOnce(false);
    const view = await renderOpenPanel();
    const file = new File(['content'], 'notes.txt', { type: 'text/plain' });

    await expect(useLiveTutorStore.getState().sendVoiceMessage?.('', [file]))
      .rejects.toThrow('Voice session could not receive the message');
    expect(useChatStore.getState().messages).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ attachments: expect.arrayContaining([expect.objectContaining({ name: 'notes.txt' })]) }),
    ]));
    act(() => view.unmount());
  });

  it('does not attach a late upload to a closed voice session', async () => {
    let finishUpload: (value: Awaited<ReturnType<typeof prepareVoiceAttachments>>) => void = () => undefined;
    vi.mocked(prepareVoiceAttachments).mockImplementation(() => new Promise((resolve) => {
      finishUpload = resolve;
    }));
    const view = await renderOpenPanel();
    const file = new File(['content'], 'notes.txt', { type: 'text/plain' });
    const upload = useLiveTutorStore.getState().sendVoiceMessage?.('', [file]);
    await waitFor(() => expect(prepareVoiceAttachments).toHaveBeenCalledOnce());
    act(() => view.unmount());

    finishUpload({
      conversation_id: 'conv_paper', version: 'late',
      material: { title: 'notes.txt', text: 'content', truncated: false },
    });

    await expect(upload).rejects.toThrow('Voice conversation changed during attachment upload');
    expect(controller.addAttachmentContext).not.toHaveBeenCalled();
  });

  it('waits for backend transcript practice and delegates the next spoken attempt', async () => {
    useChatStore.getState().setTutorProfile('english');
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('嗨你好');
    });
    await waitFor(() => expect(controller.requestResponse).toHaveBeenCalledOnce());
    expect(sendMessage).not.toHaveBeenCalled();

    await act(async () => {
      realtimeOptions?.onUserTranscript('我給你了一個對話的逐字稿，想依此練習托福英文口說');
    });
    await waitFor(() => expect(sendMessage).toHaveBeenCalledWith(
      '我給你了一個對話的逐字稿，想依此練習託福英文口說',
      'conv_paper',
      [],
      expect.objectContaining({ responseMode: 'voice', tutorProfile: 'english' }),
    ));
    expect(controller.requestResponse).toHaveBeenCalledTimes(1);

    await act(async () => {
      realtimeOptions?.onUserTranscript('I think the student is right because the library is useful.');
    });
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(2));
    expect(controller.requestResponse).toHaveBeenCalledTimes(1);
    act(() => view.unmount());
  });

  it('does not answer an older transcript after the learner starts another turn', async () => {
    useChatStore.getState().setTutorProfile('english');
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserSpeechStarted?.('turn_old');
      realtimeOptions?.onUserTurnCommitted?.('turn_old');
      realtimeOptions?.onUserSpeechStarted?.('turn_new');
      realtimeOptions?.onUserTranscript('I am still thinking', 'turn_old');
    });

    expect(controller.requestResponse).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
    await waitFor(() => expect(useChatStore.getState().messages.some((item) => item.content === 'I am still thinking')).toBe(true));

    await act(async () => {
      realtimeOptions?.onUserTurnCommitted?.('turn_new');
      realtimeOptions?.onUserTranscript('Now my answer is ready', 'turn_new');
    });
    await waitFor(() => expect(controller.requestResponse).toHaveBeenCalledOnce());
    act(() => view.unmount());
  });

  it('does not release a queued transcript when new speech begins during persistence', async () => {
    useChatStore.getState().setTutorProfile('english');
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('Let me explain', 'turn_old');
      realtimeOptions?.onUserSpeechStarted?.('turn_new');
    });

    await waitFor(() => expect(useChatStore.getState().messages.some((item) => item.content === 'Let me explain')).toBe(true));
    expect(controller.requestResponse).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('starts the English reply without waiting for local history storage', async () => {
    vi.mocked(getCurrentUserId).mockReturnValue('user_1');
    vi.mocked(databaseService.message.add).mockImplementation(
      () => new Promise<Awaited<ReturnType<typeof databaseService.message.add>>>(() => undefined),
    );
    useChatStore.getState().setTutorProfile('english');
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => realtimeOptions?.onUserTranscript('Hello there', 'turn_1'));

    await waitFor(() => expect(databaseService.message.add).toHaveBeenCalledOnce());
    expect(controller.requestResponse).toHaveBeenCalledOnce();
    act(() => view.unmount());
  });

  it('keeps voice connected after a recoverable provider turn error', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onError(new RealtimeClientError('provider_error', 'Realtime provider error (conversation_already_has_active_response)', true));
      realtimeOptions?.onStatus('speaking');
    });

    expect(useLiveTutorStore.getState().status).toBe('speaking');
    expect(useLiveTutorStore.getState().error).toBeNull();
    expect(controller.disconnect).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('shows a real provider failure and clears it after transport recovery', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => realtimeOptions?.onError(new RealtimeClientError('provider_error', 'Realtime provider error (invalid_session)')));
    expect(useLiveTutorStore.getState().error).toContain('invalid_session');
    expect(screen.getByText('Lost Connection')).toBeInTheDocument();

    act(() => realtimeOptions?.onStatus('listening'));
    expect(useLiveTutorStore.getState().error).toBeNull();
    act(() => view.unmount());
  });

  it('restarts voice when the tutor tag changes and ignores events from the old session', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledTimes(1));
    const oldOptions = vi.mocked(startRealtimeClient).mock.calls[0]?.[0];

    act(() => useChatStore.getState().setTutorProfile('english'));
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledTimes(2));
    expect(vi.mocked(startRealtimeClient).mock.calls[1]?.[0].tutorProfile).toBe('english');

    act(() => oldOptions?.onUserTranscript('stale voice turn'));
    expect(useChatStore.getState().messages.some((item) => item.content === 'stale voice turn')).toBe(false);

    act(() => useChatStore.getState().setTutorProfile('general'));
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledTimes(3));
    expect(vi.mocked(startRealtimeClient).mock.calls[2]?.[0].tutorProfile).toBe('general');
    act(() => view.unmount());
  });

  it('uses the latest tag when avatar and tutor settings change together', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledTimes(1));

    act(() => {
      useChatStore.getState().setTutorProfile('english');
      useLiveTutorStore.getState().setAvatarEnabled(true);
    });

    await waitFor(() => expect(startLiveKitAvatarClient).toHaveBeenCalledTimes(1));
    expect(vi.mocked(startLiveKitAvatarClient).mock.calls[0]?.[0].tutorProfile).toBe('english');
    act(() => view.unmount());
  });

  it('converges on the latest tag when it changes during voice startup', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledTimes(1));

    let finishEnglishStartup: ((value: typeof controller) => void) | undefined;
    vi.mocked(startRealtimeClient).mockImplementationOnce(async (options) => {
      realtimeOptions = options;
      return new Promise((resolve) => { finishEnglishStartup = resolve; });
    });
    act(() => useChatStore.getState().setTutorProfile('english'));
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledTimes(2));

    act(() => useChatStore.getState().setTutorProfile('general'));
    await act(async () => { finishEnglishStartup?.(controller); });
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledTimes(3));
    expect(vi.mocked(startRealtimeClient).mock.calls[2]?.[0].tutorProfile).toBe('general');
    act(() => view.unmount());
  });

  it('mirrors short realtime user and assistant transcripts into the chat without AREQA stream', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('你好');
    });
    act(() => {
      realtimeOptions?.onAssistantResponseStarted?.();
      realtimeOptions?.onAssistantTranscriptDelta('可以，我先簡短說。');
      realtimeOptions?.onAssistantTranscriptDone('可以，我先簡短說。');
    });

    await waitFor(() => {
      const messages = useChatStore.getState().messages;
      expect(messages).toEqual(expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '你好' }),
        expect.objectContaining({ role: 'assistant', content: '可以，我先簡短說。', isStreaming: false }),
      ]));
    });
    expect(sendMessage).not.toHaveBeenCalled();
    expect(realtimeOptions?.conversationId).toBe('conv_paper');
    act(() => view.unmount());
  });

  it('delegates deep paper voice turns to the AREQA backend voice stream with one plain readback text', async () => {
    useChatStore.getState().setTutorProfile('english');
    const finalizeVoiceResponse = vi.fn().mockResolvedValue(undefined);
    vi.mocked(sendMessage).mockImplementation(async (_content, _conversationId, _attachments, _options) => {
      return {
        completed: true,
        conversationId: 'conv_paper',
        assistantMessageId: 'assistant-deep',
        answerContent: '**深度回答** 🎯',
        finalizeVoiceResponse,
      };
    });
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTurnCommitted?.('turn-deep');
    });
    await waitFor(() => {
      expect(useChatStore.getState().messages).toEqual(expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '' }),
      ]));
    });

    await act(async () => {
      realtimeOptions?.onUserTranscript('請詳細解釋這篇論文的方法', 'turn-deep');
    });

    await waitFor(() => expect(sendMessage).toHaveBeenCalledWith(
      '請詳細解釋這篇論文的方法',
      'conv_paper',
      [],
      expect.objectContaining({
        responseMode: 'voice',
        useRag: true,
        searchMode: 'auto',
        tutorProfile: 'english',
      }),
    ));
    expect(finalizeVoiceResponse).toHaveBeenCalledWith('深度回答');
    expect(controller.speakText).toHaveBeenNthCalledWith(1, '我先整理一下重點，等我一下。');
    expect(controller.speakText).toHaveBeenNthCalledWith(2, '深度回答');
    expect(controller.cancelSpeech).toHaveBeenCalled();
    expect(useChatStore.getState().messages).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ role: 'user', content: '' }),
    ]));
    act(() => view.unmount());
  });

  it('suppresses realtime readback transcripts after backend deep answer speech starts', async () => {
    const finalizeVoiceResponse = vi.fn().mockResolvedValue(undefined);
    vi.mocked(sendMessage).mockResolvedValue({
      completed: true,
      conversationId: 'conv_paper',
      assistantMessageId: 'assistant-deep',
      answerContent: '深度回答',
      finalizeVoiceResponse,
    });
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('請詳細解釋這篇論文的方法');
    });
    act(() => {
      realtimeOptions?.onAssistantResponseStarted?.();
      realtimeOptions?.onAssistantTranscriptDelta('朗讀字幕');
      realtimeOptions?.onAssistantTranscriptDone('朗讀字幕');
      realtimeOptions?.onPlaybackState?.('stopped');
    });

    await waitFor(() => expect(controller.speakText).toHaveBeenCalledWith('深度回答'));
    expect(useChatStore.getState().messages).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ role: 'assistant', content: '朗讀字幕' }),
    ]));
    act(() => view.unmount());
  });

  it('keeps voice connected when a delegated deep answer fails', async () => {
    vi.mocked(sendMessage).mockRejectedValueOnce(new Error('backend request failed'));
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('請詳細解釋這篇論文的方法');
    });

    await waitFor(() => expect(sendMessage).toHaveBeenCalledOnce());
    expect(controller.cancelSpeech).toHaveBeenCalled();
    expect(screen.queryByText('Lost Connection')).not.toBeInTheDocument();
    expect(controller.disconnect).not.toHaveBeenCalled();
    act(() => view.unmount());
  });

  it('keeps a delegated deep answer current while its hold speech opens a realtime response', async () => {
    const finalizeVoiceResponse = vi.fn().mockResolvedValue(undefined);
    let resolveDeepAnswer: (value: Awaited<ReturnType<typeof sendMessage>>) => void = () => undefined;
    vi.mocked(sendMessage).mockImplementation(() => new Promise((resolve) => {
      resolveDeepAnswer = resolve;
    }));
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onUserTranscript('請詳細解釋這篇論文的方法');
    });
    await waitFor(() => expect(sendMessage).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onAssistantResponseStarted?.('resp-hold');
      realtimeOptions?.onAssistantTranscriptDelta('等待朗讀字幕', 'resp-hold');
      realtimeOptions?.onAssistantTranscriptDone('等待朗讀字幕', 'resp-hold');
    });
    await act(async () => {
      resolveDeepAnswer({
        completed: true,
        conversationId: 'conv_paper',
        assistantMessageId: 'assistant-deep',
        answerContent: '深度回答',
        finalizeVoiceResponse,
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(finalizeVoiceResponse).toHaveBeenCalledWith('深度回答'));
    expect(controller.speakText).toHaveBeenNthCalledWith(1, '我先整理一下重點，等我一下。');
    expect(controller.speakText).toHaveBeenNthCalledWith(2, '深度回答');
    expect(useChatStore.getState().messages).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ role: 'assistant', content: '等待朗讀字幕' }),
    ]));
    act(() => view.unmount());
  });

  it('finalizes playback state when backend readback is unavailable', async () => {
    controller.speakText.mockReturnValue(false);
    vi.mocked(sendMessage).mockResolvedValue({
      completed: true,
      conversationId: 'conv_paper',
      assistantMessageId: 'assistant-deep',
      answerContent: '深度回答',
      finalizeVoiceResponse: vi.fn().mockResolvedValue(undefined),
    });
    useChatStore.setState({
      messages: [{
        id: 'assistant-deep',
        userId: 'user_1',
        conversationId: 'conv_paper',
        role: 'assistant',
        content: '深度回答',
        createdAt: new Date('2026-09-05T00:00:00.000Z'),
        isStreaming: false,
      }],
    });
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    await act(async () => {
      realtimeOptions?.onUserTranscript('請詳細解釋這篇論文的方法');
    });

    await waitFor(() => expect(controller.speakText).toHaveBeenCalledWith('深度回答'));
    expect(useChatStore.getState().messages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'assistant-deep', voicePlayback: 'finished' }),
    ]));
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

  it('renders avatar video when a future realtime transport provides a video stream', async () => {
    useLiveTutorStore.setState({ avatarEnabled: true });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    const view = await renderOpenPanel();
    await waitFor(() => expect(startLiveKitAvatarClient).toHaveBeenCalledOnce());
    expect(startRealtimeClient).not.toHaveBeenCalled();
    const avatarStream = {
      getVideoTracks: () => [{ readyState: 'live' }],
      getAudioTracks: () => [],
      getTracks: () => [],
    } as unknown as MediaStream;

    act(() => {
      realtimeOptions?.onRemoteVideoStream?.(avatarStream);
    });

    const video = view.container.querySelector('video');
    expect(video).toBeInTheDocument();
    expect(video).toHaveAttribute('playsinline');
    expect(view.container.querySelector('[data-avatar-window="floating"]')).toBeInTheDocument();
    expect(view.container.querySelector('[data-avatar-state="video"]')).not.toBeInTheDocument();
    expect(view.container.querySelector('section')).toHaveAttribute('data-avatar-layout', 'floating');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    act(() => view.unmount());
  });

  it('renders side-pane avatar video without creating a floating avatar window', async () => {
    useLiveTutorStore.setState({ avatarEnabled: true });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    const view = await renderOpenPanel({ layout: 'side-pane' });
    await waitFor(() => expect(startLiveKitAvatarClient).toHaveBeenCalledOnce());
    const avatarStream = {
      getVideoTracks: () => [{ readyState: 'live' }],
      getAudioTracks: () => [],
      getTracks: () => [],
    } as unknown as MediaStream;

    act(() => {
      realtimeOptions?.onRemoteVideoStream?.(avatarStream);
    });

    expect(view.container.querySelector('video')).toBeInTheDocument();
    expect(view.container.querySelector('[data-avatar-state="video"]')).toBeInTheDocument();
    expect(view.container.querySelector('[data-avatar-window="floating"]')).not.toBeInTheDocument();
    expect(view.container.querySelector('section')).toHaveAttribute('data-avatar-layout', 'side-pane');
    act(() => view.unmount());
  });

  it('shows Connecting instead of the logo while waiting for avatar video', async () => {
    useLiveTutorStore.setState({ avatarEnabled: true });
    vi.mocked(startLiveKitAvatarClient).mockImplementationOnce(async (options) => {
      realtimeOptions = options;
      options.onStatus('listening');
      return controller;
    });

    const view = await renderOpenPanel();

    await waitFor(() => expect(startLiveKitAvatarClient).toHaveBeenCalledOnce());
    expect(screen.getByText('Connecting')).toBeInTheDocument();
    expect(view.container.querySelector('[data-avatar-state="fallback"]')).not.toBeInTheDocument();
    act(() => view.unmount());
  });

  it('falls back to voice-only realtime when LiveKit avatar startup fails', async () => {
    useLiveTutorStore.setState({ avatarEnabled: true });
    useChatStore.getState().setTutorProfile('english');
    vi.mocked(startLiveKitAvatarClient).mockImplementationOnce(async (options) => {
      realtimeOptions = options;
      options.onError(new Error('avatar video timeout'));
      return controller;
    });

    const view = await renderOpenPanel();

    await waitFor(() => expect(startLiveKitAvatarClient).toHaveBeenCalledOnce());
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());
    expect(vi.mocked(startLiveKitAvatarClient).mock.calls[0]?.[0].tutorProfile).toBe('english');
    expect(vi.mocked(startRealtimeClient).mock.calls[0]?.[0].tutorProfile).toBe('english');
    expect(screen.getByText('虛擬角色啟動失敗，已切回語音模式。')).toBeInTheDocument();
    expect(useLiveTutorStore.getState().avatarEnabled).toBe(false);
    act(() => view.unmount());
  });

  it('starts voice-only OpenAI Realtime by default before the avatar is requested', async () => {
    const view = await renderOpenPanel();

    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());
    expect(startLiveKitAvatarClient).not.toHaveBeenCalled();
    expect(view.container.querySelector('[data-avatar-state="fallback"]')).toBeInTheDocument();
    expect(view.container.querySelector('section')).toHaveAttribute('data-avatar-layout', 'inline');
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

  it('does not append stale assistant transcript work after the learner interrupts', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onAssistantResponseStarted?.('resp-old');
      realtimeOptions?.onAssistantTranscriptDelta('中斷前內容', 'resp-old');
      realtimeOptions?.onUserSpeechStarted?.();
      realtimeOptions?.onAssistantTranscriptDelta('中斷後舊內容', 'resp-old');
      realtimeOptions?.onAssistantTranscriptDone('中斷前內容中斷後舊內容', 'resp-old');
    });

    await waitFor(() => expect(controller.cancelSpeech).toHaveBeenCalled());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(useChatStore.getState().messages).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ role: 'assistant', content: '中斷前內容' }),
    ]));
    expect(useChatStore.getState().messages).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ role: 'assistant', content: '中斷前內容中斷後舊內容' }),
    ]));
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

  it('preserves interrupted assistant text and clears streaming state when voice mode closes', async () => {
    const view = await renderOpenPanel();
    await waitFor(() => expect(startRealtimeClient).toHaveBeenCalledOnce());

    act(() => {
      realtimeOptions?.onAssistantResponseStarted?.();
      realtimeOptions?.onAssistantTranscriptDelta('中斷前已經輸出的內容');
    });

    await waitFor(() => {
      expect(useChatStore.getState().messages.at(-1)).toEqual(expect.objectContaining({
        role: 'assistant',
        content: '中斷前已經輸出的內容',
        isStreaming: true,
      }));
    });

    act(() => {
      useLiveTutorStore.getState().requestClose();
    });

    await waitFor(() => {
      expect(useChatStore.getState().messages.at(-1)).toEqual(expect.objectContaining({
        role: 'assistant',
        content: '中斷前已經輸出的內容',
        isStreaming: false,
        voicePlayback: 'interrupted',
      }));
    });
    act(() => view.unmount());
  });
});
