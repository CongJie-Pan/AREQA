import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendMessage, regenerateMessage, editUserMessage, editAssistantMessage, switchConversation, startNewConversation, cancelCurrentStream, deleteLatestConversationTurn } from '@/services/chat';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useFeatureStore } from '@/store/features';
import { createChatStream } from '@/services/chat-stream';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import { syncService } from '@/services/syncService';
import { logger } from '@/utils/logger';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { generateConversationImage, regenerateConversationImage } from '@/services/generatedImages';

vi.mock('@/services/generatedImages', () => ({ generateConversationImage: vi.fn(), regenerateConversationImage: vi.fn() }));

vi.mock('@/store/chat', () => ({
  useChatStore: {
    getState: vi.fn(),
    setState: vi.fn(),
  },
}));

vi.mock('@/store/conversation', () => ({
  useConversationStore: {
    getState: vi.fn(),
  },
}));

vi.mock('@/services/chat-stream', () => ({
  createChatStream: vi.fn(),
}));

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      flushPendingCloudSync: vi.fn(),
    },
    message: {
      add: vi.fn(),
      delete: vi.fn(),
      deleteManyByConversationId: vi.fn(),
      getByConversationId: vi.fn(),
      getConversationDiagnostics: vi.fn(),
      flushPendingCloudSync: vi.fn(),
      update: vi.fn(),
    },
    note: {
      syncFromMessage: vi.fn().mockResolvedValue(null),
    },
  },
}));

vi.mock('@/services/syncService', () => ({
  syncService: {
    pullConversationMessages: vi.fn().mockResolvedValue(false),
  },
}));

vi.mock('@/database/db', () => ({
  getCurrentUserId: vi.fn().mockReturnValue('test-user-id'),
}));

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/config/api', () => ({
  API_CONFIG: {
    minMessageLength: 0, // Mock to 0 to test the safety intercept
    maxMessageLength: 5000,
  },
}));

vi.mock('@/utils/sanitizer', () => ({
  sanitizeMessagesForAPI: vi.fn((msgs) => msgs),
}));

describe('Chat Service', () => {
  let mockChatStore: any;
  let mockConversationStore: any;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue('test-user-id');

    mockChatStore = {
      messages: [],
      useRag: false,
      useWebSearch: false,
      searchMode: 'never',
      forceThink: false,
      addUserMessage: vi.fn(),
      addAssistantMessage: vi.fn().mockReturnValue('assistant-msg-id'),
      addAssistantMessageAt: vi.fn().mockReturnValue('assistant-msg-id'),
      updateAssistantMessage: vi.fn((id, updates) => {
        mockChatStore.messages = mockChatStore.messages.map((message) =>
          message.id === id ? { ...message, ...updates } : message
        );
      }),
      updateMessageContent: vi.fn((id, content) => {
        mockChatStore.messages = mockChatStore.messages.map((message) =>
          message.id === id ? { ...message, content } : message
        );
      }),
      setMessages: vi.fn((messages) => {
        mockChatStore.messages = messages;
      }),
      clearMessages: vi.fn(() => {
        mockChatStore.messages = [];
      }),
      startStreaming: vi.fn(),
      stopStreaming: vi.fn(),
      setError: vi.fn(),
      removeMessage: vi.fn((id) => { mockChatStore.messages = mockChatStore.messages.filter(m => m.id !== id); }),
      resetStreamingState: vi.fn(),
      appendThinkingContent: vi.fn(),
      appendContent: vi.fn(),
      endThinking: vi.fn(),
      endStreaming: vi.fn(),
      setCitations: vi.fn(),
      setAnswerBlocks: vi.fn(),
      addImageSlot: vi.fn(),
      setRagStatus: vi.fn(),
      setRagSources: vi.fn(),
    };

    mockConversationStore = {
      activeConversationId: 'test-conv-id',
      conversations: [{
        id: 'test-conv-id',
        userId: 'test-user-id',
        title: 'Existing chat',
        createdAt: new Date('2026-01-01T00:00:00.000Z'),
        updatedAt: new Date('2026-01-01T00:00:00.000Z'),
        messageCount: 1,
        lastMessagePreview: 'previous',
      }],
      createConversation: vi.fn().mockResolvedValue('new-conv-id'),
      loadConversations: vi.fn(),
      generateTitle: vi.fn(),
      selectConversation: vi.fn(),
      deleteConversation: vi.fn(),
      updateConversation: vi.fn(),
      setLoading: vi.fn(),
      setMessageHandoffLoading: vi.fn(),
    };

    vi.mocked(useChatStore.getState).mockReturnValue(mockChatStore);
    vi.mocked(useConversationStore.getState).mockReturnValue(mockConversationStore);
    vi.mocked(databaseService.message.getConversationDiagnostics).mockResolvedValue({
      messageCount: 0,
      userMessageCount: 0,
      assistantMessageCount: 0,
      pendingSyncCount: 0,
      deletionMarkerCount: 0,
      latestMessageUpdatedAt: null,
      latestQueuedAt: null,
    });
    vi.mocked(authenticatedFetch).mockResolvedValue({ ok: true, status: 200 } as Response);
    useFeatureStore.setState({ conversationHistoryDebugLogs: false });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('switchConversation', () => {
    it('logs when a history click cannot load because browser auth is unavailable', async () => {
      useFeatureStore.setState({ conversationHistoryDebugLogs: true });
      vi.mocked(getCurrentUserId).mockReturnValue(null);

      await switchConversation('target-conv');

      expect(logger.info).toHaveBeenCalledWith('chat_history_switch_requested', expect.objectContaining({
        conversationId: 'target-conv',
      }));
      expect(logger.warn).toHaveBeenCalledWith('chat_history_switch_skipped_auth', expect.objectContaining({
        conversationId: 'target-conv',
      }));
      await vi.waitFor(() => {
        expect(authenticatedFetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/conversation-history/debug-log',
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('chat_history_switch_skipped_auth'),
          }),
        );
      });
      expect(databaseService.message.getByConversationId).not.toHaveBeenCalled();
      expect(mockConversationStore.selectConversation).not.toHaveBeenCalled();
    });

    it('logs an empty conversation after selecting it', async () => {
      useFeatureStore.setState({ conversationHistoryDebugLogs: true });
      vi.mocked(databaseService.message.getByConversationId).mockResolvedValue([]);

      await switchConversation('empty-conv');

      expect(logger.info).toHaveBeenCalledWith('chat_history_switch_completed', expect.objectContaining({
        conversationId: 'empty-conv',
        displayMessageCount: 0,
      }));
      await vi.waitFor(() => {
        expect(logger.info).toHaveBeenCalledWith('chat_history_messages_committed', expect.objectContaining({
          conversationId: 'empty-conv',
          displayMessageCount: 0,
          messageCount: 0,
          pendingSyncCount: 0,
        }));
      });
      expect(authenticatedFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/conversation-history/debug-log',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('chat_history_switch_completed'),
        }),
      );
    });

    it('ignores an older slow history load after a newer selection wins', async () => {
      let resolveOlder!: (messages: never[]) => void;
      let markStarted!: () => void;
      const started = new Promise<void>((resolve) => { markStarted = resolve; });
      const olderRead = new Promise<never[]>((resolve) => { resolveOlder = resolve; });
      vi.mocked(databaseService.message.getByConversationId)
        .mockImplementationOnce(() => {
          markStarted();
          return olderRead;
        })
        .mockResolvedValueOnce([]);

      const olderSwitch = switchConversation('older-conversation');
      await started;
      try {
        await switchConversation('newer-conversation');
        expect(mockConversationStore.selectConversation).toHaveBeenLastCalledWith('newer-conversation');
      } finally {
        resolveOlder([]);
        await olderSwitch;
      }
      expect(mockConversationStore.selectConversation).toHaveBeenLastCalledWith('newer-conversation');
    });

    it('keeps the current messages visible until the target conversation messages are loaded', async () => {
      const targetMessages = [
        { id: 'target-user', role: 'user', content: 'target question', conversationId: 'target-conv' },
        { id: 'target-assistant', role: 'assistant', content: 'target answer', conversationId: 'target-conv' },
      ];
      mockChatStore.messages = [
        { id: 'current-user', role: 'user', content: 'current question', conversationId: 'current-conv' },
      ];
      vi.mocked(databaseService.message.getByConversationId).mockResolvedValue(targetMessages as any);

      await switchConversation('target-conv');

      expect(mockChatStore.clearMessages).not.toHaveBeenCalled();
      expect(databaseService.message.getByConversationId).toHaveBeenCalledWith(
        'target-conv',
        'test-user-id',
      );
      expect(mockChatStore.resetStreamingState).toHaveBeenCalled();
      expect(mockChatStore.setMessages).toHaveBeenCalledWith(targetMessages);
      expect(mockConversationStore.selectConversation).toHaveBeenCalledWith('target-conv');
      expect(mockConversationStore.setLoading).not.toHaveBeenCalled();
      expect(mockConversationStore.setMessageHandoffLoading).toHaveBeenNthCalledWith(1, true);
      expect(mockConversationStore.setMessageHandoffLoading).toHaveBeenLastCalledWith(false);
    });

    it('logs safe diagnostics when loading a conversation with pending edited-message sync state', async () => {
      useFeatureStore.setState({ conversationHistoryDebugLogs: true });
      const latestMessageUpdatedAt = new Date('2026-08-08T00:00:02.000Z');
      const latestQueuedAt = new Date('2026-08-08T00:00:03.000Z');
      const targetMessages = [
        {
          id: 'edited-user',
          role: 'user',
          content: 'edited question should not be logged',
          conversationId: 'edited-conv',
          updatedAt: latestMessageUpdatedAt,
        },
        {
          id: 'replacement-assistant',
          role: 'assistant',
          content: 'replacement answer should not be logged',
          conversationId: 'edited-conv',
          updatedAt: latestMessageUpdatedAt,
        },
      ];
      vi.mocked(databaseService.message.getByConversationId).mockResolvedValue(targetMessages as any);
      vi.mocked(databaseService.message.getConversationDiagnostics).mockResolvedValue({
        messageCount: 2,
        userMessageCount: 1,
        assistantMessageCount: 1,
        pendingSyncCount: 1,
        deletionMarkerCount: 2,
        latestMessageUpdatedAt,
        latestQueuedAt,
      });

      await switchConversation('edited-conv');

      await vi.waitFor(() => {
        expect(logger.info).toHaveBeenCalledWith(
          'chat_history_messages_committed',
          expect.objectContaining({
            component: 'chatService',
            conversationId: 'edited-conv',
            messageCount: 2,
            userMessageCount: 1,
            assistantMessageCount: 1,
            pendingSyncCount: 1,
            deletionMarkerCount: 2,
            latestMessageUpdatedAt: '2026-08-08T00:00:02.000Z',
            latestQueuedAt: '2026-08-08T00:00:03.000Z',
          }),
        );
      });
      expect(JSON.stringify(vi.mocked(logger.info).mock.calls)).not.toContain(
        'edited question should not be logged',
      );
      expect(JSON.stringify(vi.mocked(logger.info).mock.calls)).not.toContain(
        'replacement answer should not be logged',
      );
      const forwardedBodies = vi.mocked(authenticatedFetch).mock.calls.map(([, init]) => String(init?.body ?? ''));
      expect(forwardedBodies.some((body) => body.includes('chat_history_messages_committed'))).toBe(true);
      expect(JSON.stringify(forwardedBodies)).not.toContain('edited question should not be logged');
      expect(JSON.stringify(forwardedBodies)).not.toContain('replacement answer should not be logged');
    });

    it('skips conversation history diagnostics when the runtime flag is disabled', async () => {
      useFeatureStore.setState({ conversationHistoryDebugLogs: false });
      vi.mocked(databaseService.message.getByConversationId).mockResolvedValue([
        { id: 'target-user', role: 'user', content: 'target question', conversationId: 'target-conv' },
      ] as any);

      await switchConversation('target-conv');

      expect(databaseService.message.getConversationDiagnostics).not.toHaveBeenCalled();
      expect(logger.info).not.toHaveBeenCalledWith(
        'chat_history_load_started',
        expect.any(Object),
      );
      expect(logger.info).not.toHaveBeenCalledWith(
        'chat_history_messages_committed',
        expect.any(Object),
      );
      expect(authenticatedFetch).not.toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/conversation-history/debug-log',
        expect.any(Object),
      );
    });

    it('refreshes from the cloud before reading local messages for display', async () => {
      const hydratedMessages = [
        { id: 'phone-user', role: 'user', content: 'phone question', conversationId: 'phone-conv' },
        { id: 'phone-assistant', role: 'assistant', content: 'phone answer', conversationId: 'phone-conv' },
      ];
      vi.mocked(databaseService.message.getByConversationId).mockResolvedValueOnce(hydratedMessages as any);
      vi.mocked(syncService.pullConversationMessages).mockResolvedValueOnce(true);

      await switchConversation('phone-conv');

      expect(syncService.pullConversationMessages).toHaveBeenCalledWith(
        'phone-conv',
        'test-user-id',
        { authoritative: true },
      );
      expect(databaseService.message.getByConversationId).toHaveBeenCalledTimes(1);
      expect(mockChatStore.setMessages).toHaveBeenCalledWith(hydratedMessages);
      expect(mockConversationStore.selectConversation).toHaveBeenCalledWith('phone-conv');
    });

    it('reads local messages after cloud refresh even when the targeted pull reports no changes', async () => {
      const concurrentlyHydratedMessages = [
        { id: 'phone-user', role: 'user', content: 'phone question', conversationId: 'phone-conv' },
        { id: 'phone-assistant', role: 'assistant', content: 'phone answer', conversationId: 'phone-conv' },
      ];
      vi.mocked(databaseService.message.getByConversationId).mockResolvedValueOnce(concurrentlyHydratedMessages as any);
      vi.mocked(syncService.pullConversationMessages).mockResolvedValueOnce(false);

      await switchConversation('phone-conv');

      expect(syncService.pullConversationMessages).toHaveBeenCalledWith(
        'phone-conv',
        'test-user-id',
        { authoritative: true },
      );
      expect(databaseService.message.getByConversationId).toHaveBeenCalledTimes(1);
      expect(mockChatStore.setMessages).toHaveBeenCalledWith(concurrentlyHydratedMessages);
      expect(mockConversationStore.selectConversation).toHaveBeenCalledWith('phone-conv');
    });

    it('does not let a stale history load override starting a new conversation', async () => {
      let resolveOlder!: (changed: boolean) => void;
      let markStarted!: () => void;
      const started = new Promise<void>((resolve) => { markStarted = resolve; });
      const olderPull = new Promise<boolean>((resolve) => { resolveOlder = resolve; });
      vi.mocked(syncService.pullConversationMessages).mockImplementationOnce(() => {
        markStarted();
        return olderPull;
      });

      const olderSwitch = switchConversation('older-conversation');
      await started;
      await startNewConversation();
      resolveOlder(false);
      await olderSwitch;

      expect(mockChatStore.clearMessages).toHaveBeenCalled();
      expect(mockConversationStore.createConversation).toHaveBeenCalled();
      expect(mockConversationStore.selectConversation).not.toHaveBeenCalledWith('older-conversation');
    });
  });

  describe('sendMessage', () => {
    it('should complete successfully (happy path)', async () => {
      // Arrange
      mockChatStore.messages = [
        { id: 'msg-prev', role: 'user', content: 'previous' }
      ];
      const INPUT_CONTENT = 'new message';

      vi.mocked(createChatStream).mockImplementation(async (msgs, callbacks) => {
        if (callbacks.onContent) callbacks.onContent('response chunk');
        if (callbacks.onDone) await callbacks.onDone();
      });

      // Act
      const result = await sendMessage(INPUT_CONTENT);

      // Assert
      expect(mockChatStore.addUserMessage).toHaveBeenCalledWith(INPUT_CONTENT, 'test-conv-id', []);
      expect(databaseService.message.add).toHaveBeenCalledTimes(2); // user msg + assistant msg
      expect(mockChatStore.endStreaming).toHaveBeenCalled();
      expect(mockConversationStore.updateConversation).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({
          lastMessagePreview: 'response chunk',
          messageCount: 3,
        }),
      );
      expect(mockConversationStore.loadConversations).not.toHaveBeenCalled();
      expect(createChatStream).toHaveBeenCalled();
      expect(result).toEqual({ completed: true });
    });

    it('forwards streamed image slots into the chat store', async () => {
      mockChatStore.messages = [{ id: 'msg-prev', role: 'user', content: 'previous' }];
      const slot = { slotId: 'img_1', anchorAfterParagraph: 0, contentOffset: 8 };
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('圖片前段');
        callbacks.onImageSlot?.(slot);
        await callbacks.onDone();
      });

      await sendMessage('請圖解');

      expect(mockChatStore.addImageSlot).toHaveBeenCalledWith(slot);
    });

    it('does not persist guest conversations while still returning the answer', async () => {
      vi.mocked(getCurrentUserId).mockReturnValue(null);
      mockChatStore.messages = [];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('guest response');
        await callbacks.onDone();
      });

      const result = await sendMessage('guest question');

      expect(result).toEqual({ completed: true });
      expect(createChatStream).toHaveBeenCalled();
      expect(databaseService.message.add).not.toHaveBeenCalled();
    });

    it('keeps an explicit guest conversation for grounded voice follow-ups', async () => {
      vi.mocked(getCurrentUserId).mockReturnValue(null);
      mockChatStore.messages = [];
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('Try that answer again.');
        await callbacks.onDone();
      });

      await sendMessage('My answer', 'guest-speaking', [], {
        responseMode: 'voice', tutorProfile: 'english', speakingPractice: true,
      });

      expect(createChatStream).toHaveBeenCalledWith(
        expect.any(Array), expect.any(Object), expect.anything(),
        expect.any(Boolean), expect.any(Boolean), expect.any(String),
        'guest-speaking', [],
        expect.objectContaining({ responseMode: 'voice', speakingPractice: true }),
      );
    });

    it('returns an incomplete result when the stream reports an error', async () => {
      mockChatStore.messages = [{ id: 'msg-prev', role: 'user', content: 'previous' }];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onError(new Error('stream failed'));
      });

      const result = await sendMessage('new message');

      expect(result).toEqual({ completed: false });
      expect(mockChatStore.setError).toHaveBeenCalledWith(expect.objectContaining({ message: 'stream failed' }));
    });

    it('should include user message when store messages are empty (fallback mechanism)', async () => {
      // Arrange
      mockChatStore.messages = [];
      const INPUT_CONTENT = 'hello fallback';
      const EXPECTED_API_MESSAGES = [{ role: 'user', content: INPUT_CONTENT }];

      // Act
      await sendMessage(INPUT_CONTENT);

      // Assert
      expect(createChatStream).toHaveBeenCalledWith(
        EXPECTED_API_MESSAGES,
        expect.any(Object),
        expect.any(AbortSignal),
        mockChatStore.useRag,
        mockChatStore.forceThink,
        mockChatStore.searchMode,
        'test-conv-id',
        [],
        { responseMode: 'text' },
      );
    });

    it('sends attachments without persisting binary content', async () => {
      mockChatStore.messages = [];
      const attachment = new File(['attachment body'], 'notes.txt', { type: 'text/plain' });

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        await callbacks.onDone();
      });

      await sendMessage('', undefined, [attachment]);

      expect(mockChatStore.addUserMessage).toHaveBeenCalledWith(
        '請分析我附加的檔案。',
        'test-conv-id',
        [{ name: 'notes.txt', mediaType: 'text/plain', sizeBytes: attachment.size }],
      );
      expect(databaseService.message.add).toHaveBeenCalledWith(
        'test-conv-id',
        {
          role: 'user',
          content: '請分析我附加的檔案。',
          attachments: [{ name: 'notes.txt', mediaType: 'text/plain', sizeBytes: attachment.size }],
        },
      );
      expect(createChatStream).toHaveBeenLastCalledWith(
        [{ role: 'user', content: '請分析我附加的檔案。' }],
        expect.any(Object),
        expect.any(AbortSignal),
        mockChatStore.useRag,
        mockChatStore.forceThink,
        mockChatStore.searchMode,
        'test-conv-id',
        [attachment],
        { responseMode: 'text' },
      );
    });

    it('uses voice response mode without forcing hidden thinking into the spoken turn', async () => {
      mockChatStore.messages = [];
      mockChatStore.forceThink = true;
      const onVoiceContentChunk = vi.fn();

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onThinkingStart?.();
        callbacks.onThinkingContent?.('hidden reasoning');
        callbacks.onContent('口語回答');
        await callbacks.onDone();
      });

      const result = await sendMessage('請介紹這個主題', undefined, [], {
        responseMode: 'voice',
        onVoiceContentChunk,
      });

      expect(createChatStream).toHaveBeenCalledWith(
        [{ role: 'user', content: '請介紹這個主題' }],
        expect.any(Object),
        expect.any(AbortSignal),
        mockChatStore.useRag,
        false,
        mockChatStore.searchMode,
        'test-conv-id',
        [],
        { responseMode: 'voice' },
      );
      expect(onVoiceContentChunk).toHaveBeenCalledWith('口語回答');
      expect(mockChatStore.appendContent).not.toHaveBeenCalled();
      expect(mockChatStore.appendThinkingContent).not.toHaveBeenCalled();
      expect(mockChatStore.endStreaming).not.toHaveBeenCalled();
      expect(result).toEqual(expect.objectContaining({
        completed: true,
        answerContent: '口語回答',
        finalizeVoiceResponse: expect.any(Function),
      }));
    });

    it('applies per-turn retrieval overrides without mutating chat toggles', async () => {
      mockChatStore.messages = [];
      mockChatStore.useRag = false;
      mockChatStore.searchMode = 'never';

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('深度回答');
        await callbacks.onDone();
      });

      await sendMessage('請深入解釋這篇論文', 'test-conv-id', [], {
        responseMode: 'voice',
        useRag: true,
        searchMode: 'auto',
      });

      expect(createChatStream).toHaveBeenCalledWith(
        [{ role: 'user', content: '請深入解釋這篇論文' }],
        expect.any(Object),
        expect.any(AbortSignal),
        true,
        false,
        'auto',
        'test-conv-id',
        [],
        { responseMode: 'voice' },
      );
      expect(mockChatStore.useRag).toBe(false);
      expect(mockChatStore.searchMode).toBe('never');
    });

    it('keeps delegated voice answers on the session tutor profile during a tag change', async () => {
      mockChatStore.messages = [];
      mockChatStore.tutorProfile = 'general';
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('Feedback');
        await callbacks.onDone();
      });

      await sendMessage('Please explain', 'test-conv-id', [], {
        responseMode: 'voice',
        tutorProfile: 'english',
      });

      expect(createChatStream).toHaveBeenCalledWith(
        expect.any(Array),
        expect.any(Object),
        expect.any(AbortSignal),
        expect.any(Boolean),
        expect.any(Boolean),
        expect.any(String),
        'test-conv-id',
        [],
        expect.objectContaining({ tutorProfile: 'english' }),
      );
      expect(mockChatStore.tutorProfile).toBe('general');
    });

    it('preserves analysis through pending, completion, and persistence of a mixed image reply', async () => {
      mockChatStore.messages = [{ id: 'user-image', role: 'user', content: '先分析再產圖', conversationId: 'test-conv-id' }];
      const paragraph = { type: 'paragraph' as const, text: '統計顯著不代表重要。' };
      const image = { type: 'image_block' as const, provider: 'generated_image', imageUrl: '', slotId: 'image-1' };
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onAnswerBlocks?.([paragraph, { ...image, status: 'pending' }]);
        expect(mockChatStore.updateMessageContent).toHaveBeenLastCalledWith('assistant-msg-id', paragraph.text);
        callbacks.onAnswerBlocks?.([paragraph, { ...image, imageUrl: 'https://example.com/image.png' }]);
        await callbacks.onDone();
      });
      await sendMessage('先分析再產圖', 'test-conv-id');
      expect(databaseService.message.add).toHaveBeenCalledWith('test-conv-id', expect.objectContaining({ content: paragraph.text, answerBlocks: [paragraph, expect.objectContaining({ provider: 'generated_image' })] }));
    });

    it('removes streamed prose when image generation ends with an error code', async () => {
      mockChatStore.messages = [{ id: 'user-image', role: 'user', content: '請產生 ICAP 圖', conversationId: 'test-conv-id' }];
      const failure = { type: 'image_block' as const, provider: 'generated_image', imageUrl: '',
        slotId: 'image-1', status: 'error' as const, caption: 'IMAGE_PROVIDER_HTTP_402' };
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('Here is the conceptual diagram and explanation.');
        callbacks.onAnswerBlocks?.([{ type: 'paragraph', text: 'Here is the conceptual diagram.' },
          { ...failure, status: 'pending' }]);
        callbacks.onAnswerBlocks?.([failure]);
        await callbacks.onDone();
      });

      await sendMessage('請產生 ICAP 圖', 'test-conv-id');

      expect(mockChatStore.updateMessageContent).toHaveBeenLastCalledWith('assistant-msg-id', '');
      expect(databaseService.message.add).toHaveBeenCalledWith('test-conv-id', expect.objectContaining({
        content: '', answerBlocks: [failure],
      }));
    });

    it('persists an image-only tool reply and generates a first-turn title without a text preamble', async () => {
      mockChatStore.messages = [{ id: 'user-image', role: 'user', content: '請產生一張圖', conversationId: 'test-conv-id' }];
      const block = { type: 'image_block' as const, provider: 'generated_image', imageUrl: 'https://example.com/image.png', slotId: 'image-1' };
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('Here is the image I created.');
        callbacks.onAnswerBlocks?.([{ ...block, imageUrl: '', status: 'pending' }]);
        callbacks.onAnswerBlocks?.([block]);
        await callbacks.onDone();
      });
      expect(await sendMessage('請產生一張圖', 'test-conv-id')).toEqual({ completed: true });
      expect(databaseService.message.add).toHaveBeenCalledWith('test-conv-id', expect.objectContaining({ role: 'assistant', content: '', answerBlocks: [block] }));
      expect(mockChatStore.updateMessageContent).toHaveBeenCalledWith('assistant-msg-id', '');
      expect(mockConversationStore.generateTitle).toHaveBeenCalled();
    });

    it('keeps transient images visible but persists only a retryable failure without inline image data', async () => {
      mockChatStore.messages = [{ id: 'user-image', role: 'user', content: '請產圖', conversationId: 'test-conv-id' }];
      const block = { type: 'image_block' as const, provider: 'generated_image', imageUrl: 'data:image/png;base64,private', slotId: 'image-1', transient: true };
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onAnswerBlocks?.([block]);
        await callbacks.onDone();
      });
      await sendMessage('請產圖', 'test-conv-id');
      expect(mockChatStore.setAnswerBlocks).toHaveBeenCalledWith([block]);
      expect(databaseService.message.add).toHaveBeenCalledWith('test-conv-id', expect.objectContaining({
        content: expect.stringContaining('請先下載'),
        answerBlocks: [expect.objectContaining({ imageUrl: '', transient: false, status: 'error' })],
      }));
      expect(JSON.stringify(vi.mocked(databaseService.message.add).mock.calls)).not.toContain('base64,private');
    });

    it('replaces a pending image card when the stream connection fails', async () => {
      mockChatStore.messages = [{ id: 'user-image', role: 'user', content: '請產圖', conversationId: 'test-conv-id' }];
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onAnswerBlocks?.([{ type: 'image_block', provider: 'generated_image', imageUrl: '', slotId: 'image-1', status: 'pending', safetyStatus: 'unavailable', matchConfidence: 0, topic: '', purpose: 'diagram', sourceUrl: '', sourceDomain: '', caption: '' }]);
        callbacks.onError(new Error('connection interrupted'));
      });
      await sendMessage('請產圖', 'test-conv-id');
      expect(mockChatStore.setAnswerBlocks).toHaveBeenLastCalledWith([expect.objectContaining({ status: 'error', caption: 'IMAGE_STREAM_INTERRUPTED' })]);
      expect(mockChatStore.updateMessageContent).toHaveBeenLastCalledWith('assistant-msg-id', '');
    });

    it('ignores late image resolution and completion after the user stops the stream', async () => {
      mockChatStore.messages = [{ id: 'user-image', role: 'user', content: '請產圖', conversationId: 'test-conv-id' }];
      mockChatStore.currentStreamingId = 'assistant-msg-id';
      mockChatStore.currentContent = '';
      mockChatStore.thinkingContent = '';
      mockChatStore.setAnswerBlocks.mockImplementation((blocks) => { mockChatStore.currentAnswerBlocks = blocks; });
      const block = { type: 'image_block' as const, provider: 'generated_image', imageUrl: '', slotId: 'image-1', status: 'pending' as const, safetyStatus: 'unavailable' as const, matchConfidence: 0, topic: '', purpose: 'diagram' as const, sourceUrl: '', sourceDomain: '', caption: '' };
      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onAnswerBlocks?.([block]);
        await cancelCurrentStream();
        callbacks.onAnswerBlocks?.([{ ...block, status: 'resolved', imageUrl: 'https://example.com/late.png' }]);
        await callbacks.onDone();
      });
      expect(await sendMessage('請產圖', 'test-conv-id')).toEqual({ completed: false });
      expect(mockChatStore.setAnswerBlocks).toHaveBeenLastCalledWith([expect.objectContaining({ status: 'error' })]);
      expect(mockConversationStore.generateTitle).not.toHaveBeenCalled();
    });

    it('keeps generated image facts in follow-up context without forwarding private storage URLs', async () => {
      mockChatStore.messages = [
        { id: 'previous-user', role: 'user', content: '產圖', conversationId: 'test-conv-id' },
        { id: 'previous-image', role: 'assistant', content: '', conversationId: 'test-conv-id', answerBlocks: [{ type: 'image_block', provider: 'generated_image', imageUrl: 'https://example.com/private?token=secret', visionSummary: '效果量與樣本數的關係' }] },
        { id: 'followup', role: 'user', content: '修改上圖的標題', conversationId: 'test-conv-id' },
      ];
      await sendMessage('修改上圖的標題', 'test-conv-id');
      const messages = vi.mocked(createChatStream).mock.calls[0][0];
      expect(messages).toContainEqual(expect.objectContaining({ role: 'assistant', content: expect.stringContaining('效果量與樣本數的關係') }));
      expect(JSON.stringify(messages)).not.toContain('token=secret');
    });

    it('ends a pending generated image on cancellation rather than leaving a loading card', async () => {
      mockChatStore.currentStreamingId = 'assistant-image';
      mockChatStore.currentContent = '';
      mockChatStore.thinkingContent = '';
      mockChatStore.currentAnswerBlocks = [{ type: 'image_block', provider: 'generated_image', status: 'pending', slotId: 'image-1' }];
      await cancelCurrentStream();
      expect(mockChatStore.setAnswerBlocks).toHaveBeenCalledWith([expect.objectContaining({ status: 'error', caption: '圖片生成已停止' })]);
      expect(databaseService.message.add).toHaveBeenCalledWith('test-conv-id', expect.objectContaining({ answerBlocks: [expect.objectContaining({ status: 'error' })] }));
      expect(mockChatStore.resetStreamingState).toHaveBeenCalled();
    });

    it('removes an empty streaming assistant placeholder when cancellation happens before content', async () => {
      mockChatStore.currentStreamingId = 'assistant-empty';
      mockChatStore.currentContent = '';
      mockChatStore.isThinking = false;
      mockChatStore.thinkingContent = '';

      await cancelCurrentStream();

      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('assistant-empty');
      expect(mockChatStore.endStreaming).not.toHaveBeenCalled();
      expect(databaseService.message.add).not.toHaveBeenCalled();
      expect(mockChatStore.resetStreamingState).toHaveBeenCalled();
    });

    it('should not call createChatStream and set error when messages are empty after preparation (safety intercept)', async () => {
      // Arrange
      mockChatStore.messages = [];
      // Bypass validateMessageContent via minMessageLength=0, but result in empty sanitizedContent
      const INPUT_CONTENT = '   '; 

      // Act
      await sendMessage(INPUT_CONTENT);

      // Assert
      expect(mockChatStore.resetStreamingState).toHaveBeenCalled();
      expect(mockChatStore.setError).toHaveBeenCalledWith(
        expect.objectContaining({ message: '無法準備對話內容，請重新嘗試。' })
      );
      expect(createChatStream).not.toHaveBeenCalled();
    });
  });

  describe('regenerateMessage', () => {
    it('routes generated images to image regeneration instead of a text stream', async () => {
      mockChatStore.messages = [{ id: 'image-reply', role: 'assistant', content: '',
        answerBlocks: [{ type: 'image_block', provider: 'generated_image', status: 'pending' }],
      }];
      await regenerateMessage('image-reply');
      expect(regenerateConversationImage).toHaveBeenCalledWith('image-reply');
      expect(createChatStream).not.toHaveBeenCalled();
      expect(mockChatStore.startStreaming).not.toHaveBeenCalled();
    });
    it('should regenerate successfully (happy path)', async () => {
      // Arrange
      const TARGET_MSG_ID = 'msg-1';
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'hello', conversationId: 'test-conv-id' },
        { id: TARGET_MSG_ID, role: 'assistant', content: 'AI reply', conversationId: 'test-conv-id' }
      ];

      vi.mocked(createChatStream).mockImplementation(async (msgs, callbacks) => {
        if (callbacks.onContent) callbacks.onContent('new response chunk');
        if (callbacks.onDone) await callbacks.onDone();
      });

      // Act
      await regenerateMessage(TARGET_MSG_ID);

      // Assert
      expect(mockChatStore.removeMessage).not.toHaveBeenCalled();
      expect(mockChatStore.addAssistantMessageAt).not.toHaveBeenCalled();
      expect(mockChatStore.startStreaming).toHaveBeenCalledWith(TARGET_MSG_ID);
      expect(mockChatStore.updateAssistantMessage).toHaveBeenCalledWith(
        TARGET_MSG_ID,
        expect.objectContaining({ content: '', isStreaming: true }),
      );
      expect(databaseService.message.delete).not.toHaveBeenCalled();
      expect(databaseService.message.update).toHaveBeenCalledWith(
        TARGET_MSG_ID,
        expect.objectContaining({ role: 'assistant', content: 'new response chunk' }),
      );
      expect(mockConversationStore.updateConversation).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({
          lastMessagePreview: 'new response chunk',
          messageCount: 1,
        }),
      );
      expect(mockConversationStore.loadConversations).not.toHaveBeenCalled();
      expect(mockChatStore.endStreaming).toHaveBeenCalled();
    });

    it('should not call createChatStream when apiMessages is empty (safety intercept)', async () => {
      // Arrange
      const TARGET_MSG_ID = 'msg-1';
      mockChatStore.messages = [
        { id: TARGET_MSG_ID, role: 'assistant', content: 'AI reply' }
      ];

      // Act
      await regenerateMessage(TARGET_MSG_ID);

      // Assert
      expect(mockChatStore.resetStreamingState).toHaveBeenCalled();
      expect(mockChatStore.setError).toHaveBeenCalledWith(
        expect.objectContaining({ message: '無法準備對話內容（歷史記錄為空），無法重新生成。' })
      );
      expect(mockChatStore.removeMessage).not.toHaveBeenCalled();
      expect(databaseService.message.delete).not.toHaveBeenCalled();
      expect(createChatStream).not.toHaveBeenCalled();
    });

    it('preserves history and replaces the final assistant message in place', async () => {
      const targetId = 'assistant-final';
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'first question', conversationId: 'test-conv-id' },
        { id: 'assistant-1', role: 'assistant', content: 'first answer', conversationId: 'test-conv-id' },
        { id: targetId, role: 'assistant', content: 'old final answer', conversationId: 'test-conv-id' },
      ];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('replacement');
        await callbacks.onDone();
      });

      await regenerateMessage(targetId);

      expect(mockChatStore.removeMessage).not.toHaveBeenCalled();
      expect(databaseService.message.delete).not.toHaveBeenCalled();
      expect(mockChatStore.addAssistantMessageAt).not.toHaveBeenCalled();
      expect(mockChatStore.startStreaming).toHaveBeenCalledWith(targetId);
      expect(createChatStream).toHaveBeenCalledWith(
        [
          { role: 'user', content: 'first question' },
          { role: 'assistant', content: 'first answer' },
        ],
        expect.any(Object),
        expect.any(AbortSignal),
        false,
        false,
        'never',
        'test-conv-id',
        [],
        expect.objectContaining({ tutorProfile: undefined }),
      );
    });

    it('replaces the target assistant in place and preserves later messages', async () => {
      const targetId = 'assistant-middle';
      const laterUserId = 'user-later';
      const laterAssistantId = 'assistant-later';
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'first question', conversationId: 'test-conv-id' },
        { id: 'assistant-1', role: 'assistant', content: 'first answer', conversationId: 'test-conv-id' },
        { id: targetId, role: 'assistant', content: 'old answer', conversationId: 'test-conv-id' },
        { id: laterUserId, role: 'user', content: 'later question', conversationId: 'test-conv-id' },
        { id: laterAssistantId, role: 'assistant', content: 'later answer', conversationId: 'test-conv-id' },
      ];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('replacement');
        await callbacks.onDone();
      });

      await regenerateMessage(targetId);

      expect(mockChatStore.removeMessage).not.toHaveBeenCalled();
      expect(databaseService.message.delete).not.toHaveBeenCalled();
      expect(mockChatStore.addAssistantMessageAt).not.toHaveBeenCalled();
      expect(mockChatStore.startStreaming).toHaveBeenCalledWith(targetId);
      expect(createChatStream).toHaveBeenCalledWith(
        [
          { role: 'user', content: 'first question' },
          { role: 'assistant', content: 'first answer' },
        ],
        expect.any(Object),
        expect.any(AbortSignal),
        false,
        false,
        'never',
        'test-conv-id',
        [],
        expect.objectContaining({ tutorProfile: undefined }),
      );
    });

    it('regenerates guest messages from in-memory history without persistence', async () => {
      vi.mocked(getCurrentUserId).mockReturnValue(null);
      const targetId = 'guest-assistant';
      mockConversationStore.activeConversationId = null;
      mockChatStore.messages = [
        { id: 'guest-user', role: 'user', content: 'guest question', conversationId: 'guest-conv' },
        { id: targetId, role: 'assistant', content: 'old answer', conversationId: 'guest-conv' },
      ];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('guest replacement');
        await callbacks.onDone();
      });

      await regenerateMessage(targetId);

      expect(createChatStream).toHaveBeenCalledWith(
        [{ role: 'user', content: 'guest question' }],
        expect.any(Object),
        expect.any(AbortSignal),
        false,
        false,
        'never',
        'guest-conv',
        [],
        expect.objectContaining({ tutorProfile: undefined }),
      );
      expect(databaseService.message.delete).not.toHaveBeenCalled();
      expect(databaseService.message.update).not.toHaveBeenCalled();
      expect(mockChatStore.startStreaming).toHaveBeenCalledWith(targetId);
    });
  });

  describe('editUserMessage', () => {
    it('regenerates an edited image through the image capability instead of chat', async () => {
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'old drawing', conversationId: 'test-conv-id' },
        { id: 'image-1', role: 'assistant', content: '', conversationId: 'test-conv-id', answerBlocks: [{
          type: 'image_block', provider: 'generated_image', imageUrl: 'https://example.test/image.png',
          generationRequest: { language: 'en', referenceBrief: 'A factual source', conversationContext: 'user: blue book' },
        }] },
        { id: 'later-1', role: 'user', content: 'later turn', conversationId: 'test-conv-id' },
      ];
      vi.mocked(generateConversationImage).mockResolvedValueOnce({ completed: true, persisted: true });

      await editUserMessage('user-1', 'draw a blue book');

      expect(generateConversationImage).toHaveBeenCalledWith('draw a blue book', 'test-conv-id', 'en', false,
        expect.objectContaining({ assistantMessageId: 'image-1', referenceBrief: 'A factual source',
          conversationContext: 'user: blue book', replaceExistingText: true }));
      expect(createChatStream).not.toHaveBeenCalled();
      expect(databaseService.message.update).toHaveBeenCalledWith('user-1', expect.objectContaining({ content: 'draw a blue book' }));
      expect(databaseService.message.deleteManyByConversationId).toHaveBeenCalledWith('test-conv-id', ['later-1']);
    });

    it('keeps the original image branch when edited image generation fails', async () => {
      const original = [
        { id: 'user-1', role: 'user' as const, content: 'old drawing', conversationId: 'test-conv-id' },
        { id: 'image-1', role: 'assistant' as const, content: '', conversationId: 'test-conv-id', answerBlocks: [{
          type: 'image_block' as const, provider: 'generated_image', imageUrl: 'https://example.test/image.png',
        }] },
      ];
      mockChatStore.messages = original;
      vi.mocked(generateConversationImage).mockResolvedValueOnce({ completed: false });

      await expect(editUserMessage('user-1', 'draw a blue book')).rejects.toThrow('Edited image generation failed');
      expect(mockChatStore.setMessages).toHaveBeenCalledWith(original);
      expect(createChatStream).not.toHaveBeenCalled();
      expect(databaseService.message.update).not.toHaveBeenCalled();
    });

    it('commits a regenerated branch only after the edited response completes', async () => {
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'old question', conversationId: 'test-conv-id' },
        { id: 'assistant-old', role: 'assistant', content: 'old answer', conversationId: 'test-conv-id' },
        { id: 'user-later', role: 'user', content: 'later question', conversationId: 'test-conv-id' },
      ];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('new answer');
        await callbacks.onDone();
      });

      await editUserMessage('user-1', 'edited question');

      expect(mockChatStore.updateMessageContent).toHaveBeenCalledWith('user-1', 'edited question');
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('assistant-old');
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('user-later');
      expect(databaseService.message.update).toHaveBeenCalledWith('user-1', expect.objectContaining({
        content: 'edited question',
      }));
      expect(databaseService.message.deleteManyByConversationId).toHaveBeenCalledWith(
        'test-conv-id',
        ['assistant-old', 'user-later'],
      );
      expect(databaseService.message.add).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({
          id: 'assistant-msg-id',
          role: 'assistant',
          content: 'new answer',
        }),
      );
      expect(createChatStream).toHaveBeenCalledWith(
        [{ role: 'user', content: 'edited question' }],
        expect.any(Object),
        expect.any(AbortSignal),
        false,
        false,
        'never',
        'test-conv-id',
        [],
        expect.objectContaining({ tutorProfile: undefined }),
      );
    });

    it('restores the original branch when regenerated edit streaming fails', async () => {
      const originalMessages = [
        { id: 'user-1', role: 'user' as const, content: 'old question', conversationId: 'test-conv-id' },
        { id: 'assistant-old', role: 'assistant' as const, content: 'old answer', conversationId: 'test-conv-id' },
        { id: 'user-later', role: 'user' as const, content: 'later question', conversationId: 'test-conv-id' },
      ];
      mockChatStore.messages = originalMessages;
      vi.mocked(createChatStream).mockRejectedValueOnce(new Error('network failed'));

      await expect(editUserMessage('user-1', 'edited question')).rejects.toThrow('network failed');

      expect(mockChatStore.setMessages).toHaveBeenCalledWith(originalMessages);
      expect(databaseService.message.update).not.toHaveBeenCalled();
      expect(databaseService.message.add).not.toHaveBeenCalled();
      expect(databaseService.message.deleteManyByConversationId).not.toHaveBeenCalled();
    });

    it('keeps original attachment context when regenerating from an edited user query', async () => {
      mockChatStore.messages = [
        {
          id: 'user-1',
          role: 'user',
          content: 'old question',
          conversationId: 'test-conv-id',
          attachments: [{ name: 'diagram.png', mediaType: 'image/png', sizeBytes: 2048 }],
        },
        { id: 'assistant-old', role: 'assistant', content: 'old answer', conversationId: 'test-conv-id' },
      ];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('new answer');
        await callbacks.onDone();
      });

      await editUserMessage('user-1', 'edited question');

      expect(createChatStream).toHaveBeenCalledWith(
        [
          {
            role: 'user',
            content: expect.stringContaining('edited question\n[Original attachments retained for context; binary file bytes are not resent on edit]\n1. diagram.png (image/png, 2 KB)'),
          },
        ],
        expect.any(Object),
        expect.any(AbortSignal),
        false,
        false,
        'never',
        'test-conv-id',
        [],
        expect.objectContaining({ tutorProfile: undefined }),
      );
      expect(databaseService.message.update).toHaveBeenCalledWith('user-1', expect.objectContaining({
        content: 'edited question',
      }));
    });
  });

  describe('editAssistantMessage', () => {
    it('updates a completed assistant reply and preserves image answer blocks', async () => {
      const imageBlock = {
        type: 'image_block' as const,
        slotId: 'visual-1',
        topic: 'Forest plot',
        purpose: 'diagram',
        imageUrl: 'https://example.com/forest.png',
        sourceUrl: 'https://example.com/source',
        sourceDomain: 'example.com',
        caption: 'Forest plot example',
        safetyStatus: 'pass' as const,
        matchConfidence: 0.6,
      };
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'question', conversationId: 'test-conv-id' },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'old answer',
          conversationId: 'test-conv-id',
          answerBlocks: [{ type: 'paragraph', text: 'old answer' }, imageBlock],
        },
      ];

      await editAssistantMessage('assistant-1', ' **edited** answer ');

      expect(mockChatStore.updateAssistantMessage).toHaveBeenCalledWith('assistant-1', {
        content: '**edited** answer',
        answerBlocks: [{ type: 'paragraph', text: '**edited** answer' }, imageBlock],
        streamImageSlots: undefined,
        isStreaming: false,
        voicePlayback: undefined,
        updatedAt: expect.any(Date),
      });
      expect(databaseService.message.update).toHaveBeenCalledWith('assistant-1', {
        content: '**edited** answer',
        answerBlocks: [{ type: 'paragraph', text: '**edited** answer' }, imageBlock],
        updatedAt: expect.any(Date),
      });
      expect(databaseService.note.syncFromMessage).toHaveBeenCalledWith(expect.objectContaining({
        id: 'assistant-1',
        content: '**edited** answer',
        answerBlocks: [{ type: 'paragraph', text: '**edited** answer' }, imageBlock],
      }));
      expect(mockConversationStore.updateConversation).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({
          lastMessagePreview: '**edited** answer',
        }),
      );
    });

    it('rejects editing a streaming assistant reply', async () => {
      mockChatStore.currentStreamingId = 'assistant-1';
      mockChatStore.messages = [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'partial',
          conversationId: 'test-conv-id',
          isStreaming: true,
        },
      ];

      await expect(editAssistantMessage('assistant-1', 'edited')).rejects.toThrow(
        'Cannot edit a streaming assistant message',
      );

      expect(mockChatStore.updateAssistantMessage).not.toHaveBeenCalled();
      expect(databaseService.message.update).not.toHaveBeenCalled();
    });

    it('does not update the assistant store when persistence fails', async () => {
      mockChatStore.messages = [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'old answer',
          conversationId: 'test-conv-id',
        },
      ];
      vi.mocked(databaseService.message.update).mockRejectedValueOnce(new Error('disk failed'));

      await expect(editAssistantMessage('assistant-1', 'edited answer')).rejects.toThrow('disk failed');

      expect(mockChatStore.updateAssistantMessage).not.toHaveBeenCalled();
      expect(databaseService.note.syncFromMessage).not.toHaveBeenCalled();
    });

    it('updates the assistant reply even when linked note mirroring fails', async () => {
      mockChatStore.messages = [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'old answer',
          conversationId: 'test-conv-id',
        },
      ];
      vi.mocked(databaseService.note.syncFromMessage).mockRejectedValueOnce(new Error('note failed'));

      await editAssistantMessage('assistant-1', 'edited answer');

      expect(mockChatStore.updateAssistantMessage).toHaveBeenCalledWith('assistant-1', expect.objectContaining({
        content: 'edited answer',
        isStreaming: false,
      }));
      expect(mockConversationStore.updateConversation).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({ lastMessagePreview: 'edited answer' }),
      );
    });
  });

  describe('deleteLatestConversationTurn', () => {
    it('deletes unpaired user queries that belong to the latest assistant turn block', async () => {
      mockChatStore.messages = [
        { id: 'orphan-user', role: 'user', content: 'unanswered', conversationId: 'test-conv-id' },
        { id: 'user-2', role: 'user', content: 'retry', conversationId: 'test-conv-id' },
        { id: 'assistant-2', role: 'assistant', content: 'answer', conversationId: 'test-conv-id' },
      ];

      await deleteLatestConversationTurn('assistant-2');

      expect(mockChatStore.messages).toEqual([]);
      expect(databaseService.message.deleteManyByConversationId).toHaveBeenCalledWith(
        'test-conv-id',
        ['orphan-user', 'user-2', 'assistant-2'],
      );
    });

    it('deletes the bottom assistant reply and paired user query from store and persistence', async () => {
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'first question', conversationId: 'test-conv-id' },
        { id: 'assistant-1', role: 'assistant', content: 'first answer', conversationId: 'test-conv-id' },
        { id: 'user-2', role: 'user', content: 'latest question', conversationId: 'test-conv-id' },
        { id: 'assistant-2', role: 'assistant', content: 'latest answer', conversationId: 'test-conv-id' },
      ];

      await deleteLatestConversationTurn('assistant-2');

      expect(databaseService.message.deleteManyByConversationId).toHaveBeenCalledWith(
        'test-conv-id',
        ['user-2', 'assistant-2'],
      );
      expect(mockChatStore.removeMessage).toHaveBeenNthCalledWith(1, 'user-2');
      expect(mockChatStore.removeMessage).toHaveBeenNthCalledWith(2, 'assistant-2');
      expect(mockChatStore.resetStreamingState).toHaveBeenCalled();
      expect(mockConversationStore.updateConversation).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({
          lastMessagePreview: 'first answer',
          messageCount: 2,
        }),
      );
    });

    it('rejects deleting a non-latest assistant reply', async () => {
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'first question', conversationId: 'test-conv-id' },
        { id: 'assistant-1', role: 'assistant', content: 'first answer', conversationId: 'test-conv-id' },
        { id: 'user-2', role: 'user', content: 'latest question', conversationId: 'test-conv-id' },
        { id: 'assistant-2', role: 'assistant', content: 'latest answer', conversationId: 'test-conv-id' },
      ];

      await expect(deleteLatestConversationTurn('assistant-1')).rejects.toThrow(
        'Only the latest completed assistant reply can be deleted',
      );

      expect(databaseService.message.deleteManyByConversationId).not.toHaveBeenCalled();
      expect(mockChatStore.removeMessage).not.toHaveBeenCalled();
    });

    it('uses the clicked assistant message conversation when active conversation state is stale', async () => {
      mockConversationStore.activeConversationId = 'stale-conv-id';
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'first question', conversationId: 'test-conv-id' },
        { id: 'assistant-1', role: 'assistant', content: 'first answer', conversationId: 'test-conv-id' },
        { id: 'user-2', role: 'user', content: 'latest question', conversationId: 'test-conv-id' },
        { id: 'assistant-2', role: 'assistant', content: 'latest answer', conversationId: 'test-conv-id' },
      ];

      await deleteLatestConversationTurn('assistant-2');

      expect(databaseService.message.deleteManyByConversationId).toHaveBeenCalledWith(
        'test-conv-id',
        ['user-2', 'assistant-2'],
      );
      expect(mockConversationStore.updateConversation).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({
          lastMessagePreview: 'first answer',
          messageCount: 2,
        }),
      );
    });

    it('deletes every assistant fragment after the latest paired user query', async () => {
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'first question', conversationId: 'test-conv-id' },
        { id: 'assistant-1', role: 'assistant', content: 'first answer', conversationId: 'test-conv-id' },
        { id: 'user-2', role: 'user', content: 'latest question', conversationId: 'test-conv-id' },
        { id: 'assistant-2a', role: 'assistant', content: 'latest answer part 1', conversationId: 'test-conv-id' },
        { id: 'assistant-2b', role: 'assistant', content: 'latest answer part 2', conversationId: 'test-conv-id' },
      ];

      await deleteLatestConversationTurn('assistant-2b');

      expect(databaseService.message.deleteManyByConversationId).toHaveBeenCalledWith(
        'test-conv-id',
        ['user-2', 'assistant-2a', 'assistant-2b'],
      );
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('user-2');
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('assistant-2a');
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('assistant-2b');
    });

    it('still removes the visible turn when persistence deletion fails', async () => {
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'first question', conversationId: 'test-conv-id' },
        { id: 'assistant-1', role: 'assistant', content: 'first answer', conversationId: 'test-conv-id' },
        { id: 'user-2', role: 'user', content: 'latest question', conversationId: 'test-conv-id' },
        { id: 'assistant-2', role: 'assistant', content: 'latest answer', conversationId: 'test-conv-id' },
      ];
      vi.mocked(databaseService.message.deleteManyByConversationId).mockRejectedValueOnce(
        new Error('IndexedDB unavailable'),
      );

      await deleteLatestConversationTurn('assistant-2');

      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('user-2');
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('assistant-2');
      expect(mockConversationStore.updateConversation).toHaveBeenCalledWith(
        'test-conv-id',
        expect.objectContaining({ lastMessagePreview: 'first answer', messageCount: 2 }),
      );
    });
  });
});
