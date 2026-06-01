import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useConversationStore } from '@/store/conversation/store';
import { databaseService } from '@/services/database';

vi.mock('@/services/database', () => ({
  databaseService: {
    conversation: {
      getAll: vi.fn().mockResolvedValue([]),
      create: vi.fn().mockResolvedValue({ id: 'new-id', title: 'New' }),
      delete: vi.fn().mockResolvedValue(undefined),
      update: vi.fn().mockResolvedValue(undefined),
    },
  },
}));

describe('Conversation Store', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useConversationStore.setState({
      conversations: [],
      activeConversationId: null,
      isLoading: false,
      error: null,
      streamingTitles: {},
    });
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('generateTitle', () => {
    it('should handle SSE stream and update title correctly', async () => {
      const MOCK_ID = 'conv-1';
      const MOCK_MESSAGES = [{ role: 'user', content: 'test msg' }];
      
      const encoder = new TextEncoder();
      const chunks = [
        'data: {"content": "Test "}\n\n',
        'data: {"content": "Title"}\n\n',
        'data: [DONE]\n\n'
      ];
      
      const stream = new ReadableStream({
        start(controller) {
          for (const chunk of chunks) {
            controller.enqueue(encoder.encode(chunk));
          }
          controller.close();
        }
      });

      vi.mocked(global.fetch).mockResolvedValue({
        ok: true,
        body: stream,
      } as any);

      // Record states
      const states: (string | undefined)[] = [];
      const unsubscribe = useConversationStore.subscribe((state) => {
        const title = state.streamingTitles[MOCK_ID];
        if (states[states.length - 1] !== title) {
          states.push(title);
        }
      });

      // Act
      await useConversationStore.getState().generateTitle(MOCK_ID, MOCK_MESSAGES);
      
      // Unsubscribe
      unsubscribe();

      // states should include '', 'Test ', 'Test Title', and finally undefined (when cleared)
      // Sometimes it might batch updates, but it should definitely contain 'Test Title' before undefined
      expect(states).toContain('');
      expect(states).toContain('Test Title');
      expect(states[states.length - 1]).toBeUndefined();

      // Assert Database update
      expect(global.fetch).toHaveBeenCalledWith('/api/title', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: MOCK_MESSAGES }),
      });

      expect(databaseService.conversation.update).toHaveBeenCalledWith(MOCK_ID, {
        title: 'Test Title'
      });
      expect(databaseService.conversation.getAll).toHaveBeenCalled();
    });

    it('should handle API errors gracefully', async () => {
      const MOCK_ID = 'conv-2';
      
      vi.mocked(global.fetch).mockResolvedValue({
        ok: false,
      } as any);

      await useConversationStore.getState().generateTitle(MOCK_ID, []);

      // Assert
      expect(databaseService.conversation.update).not.toHaveBeenCalled();
      expect(useConversationStore.getState().streamingTitles[MOCK_ID]).toBeUndefined();
    });
  });
});
