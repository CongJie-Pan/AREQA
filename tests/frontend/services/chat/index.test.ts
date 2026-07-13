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
      expect(mockChatStore.addUserMessage).toHaveBeenCalledWith(INPUT_CONTENT, 'test-conv-id');
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
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith(TARGET_MSG_ID);
      expect(databaseService.message.delete).toHaveBeenCalledWith(TARGET_MSG_ID);
      expect(databaseService.message.add).toHaveBeenCalled(); // the new assistant message
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
      expect(mockChatStore.removeMessage).toHaveBeenCalledWith(TARGET_MSG_ID);
      expect(databaseService.message.delete).toHaveBeenCalledWith(TARGET_MSG_ID);
      expect(mockChatStore.resetStreamingState).toHaveBeenCalled();
      expect(mockChatStore.setError).toHaveBeenCalledWith(
        expect.objectContaining({ message: '無法準備對話內容（歷史記錄為空），無法重新生成。' })
      );
      expect(createChatStream).not.toHaveBeenCalled();
    });
  });
});
