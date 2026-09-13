import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendMessage, regenerateMessage, editUserMessage, switchConversation, cancelCurrentStream, deleteLatestConversationTurn } from '@/services/chat';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { createChatStream } from '@/services/chat-stream';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';

vi.mock('@/store/chat', () => ({
  useChatStore: {
    getState: vi.fn(),
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
    message: {
      add: vi.fn(),
      delete: vi.fn(),
      deleteManyByConversationId: vi.fn(),
      getByConversationId: vi.fn(),
      update: vi.fn(),
    },
  },
}));

vi.mock('@/database/db', () => ({
  getCurrentUserId: vi.fn().mockReturnValue('test-user-id'),
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
      updateAssistantMessage: vi.fn(),
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
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('switchConversation', () => {
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
      );
      expect(databaseService.message.delete).not.toHaveBeenCalled();
      expect(databaseService.message.update).not.toHaveBeenCalled();
      expect(mockChatStore.startStreaming).toHaveBeenCalledWith(targetId);
    });
  });

  describe('editUserMessage', () => {
    it('deletes superseded assistant replies before saving the edited response', async () => {
      mockChatStore.messages = [
        { id: 'user-1', role: 'user', content: 'old question', conversationId: 'test-conv-id' },
        { id: 'assistant-old', role: 'assistant', content: 'old answer', conversationId: 'test-conv-id' },
      ];

      vi.mocked(createChatStream).mockImplementation(async (_messages, callbacks) => {
        callbacks.onContent('new answer');
        await callbacks.onDone();
      });

      await editUserMessage('user-1', 'edited question');

      expect(mockChatStore.updateMessageContent).toHaveBeenCalledWith('user-1', 'edited question');
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith('assistant-old');
      expect(databaseService.message.update).toHaveBeenCalledWith('user-1', { content: 'edited question' });
      expect(databaseService.message.delete).toHaveBeenCalledWith('assistant-old');
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
      );
    });
  });

  describe('deleteLatestConversationTurn', () => {
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
