import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendMessage, regenerateMessage } from '@/services/chat';
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
      searchMode: 'auto',
      forceThink: false,
      addUserMessage: vi.fn(),
      addAssistantMessage: vi.fn().mockReturnValue('assistant-msg-id'),
      addAssistantMessageAt: vi.fn().mockReturnValue('assistant-msg-id'),
      updateAssistantMessage: vi.fn(),
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
      setRagStatus: vi.fn(),
      setRagSources: vi.fn(),
    };

    mockConversationStore = {
      activeConversationId: 'test-conv-id',
      createConversation: vi.fn().mockResolvedValue('new-conv-id'),
      loadConversations: vi.fn(),
      generateTitle: vi.fn(),
      selectConversation: vi.fn(),
      deleteConversation: vi.fn(),
    };

    vi.mocked(useChatStore.getState).mockReturnValue(mockChatStore);
    vi.mocked(useConversationStore.getState).mockReturnValue(mockConversationStore);
  });

  afterEach(() => {
    vi.restoreAllMocks();
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
      expect(createChatStream).toHaveBeenCalled();
      expect(result).toEqual({ completed: true });
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
        'test-conv-id'
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
      );
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
        'auto',
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
        'auto',
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
        'auto',
        'guest-conv',
      );
      expect(databaseService.message.delete).not.toHaveBeenCalled();
      expect(databaseService.message.update).not.toHaveBeenCalled();
      expect(mockChatStore.startStreaming).toHaveBeenCalledWith(targetId);
    });
  });
});
