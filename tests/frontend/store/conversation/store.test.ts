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

vi.mock('@/database/db', () => ({
  getCurrentUserId: vi.fn().mockReturnValue('test-user-id'),
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

  it('loads conversations only for the authenticated user', async () => {
    await useConversationStore.getState().loadConversations('user-1');

    expect(databaseService.conversation.getAll).toHaveBeenCalledWith('user-1');
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

    it('should not persist malformed model output as a title', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            'data: {"content": "**標題：** 請根據上述對話內容"}\n\n'
          ));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        },
      });
      vi.mocked(global.fetch).mockResolvedValue({ ok: true, body: stream } as any);

      await useConversationStore.getState().generateTitle(
        'conv-malformed',
        [{ role: 'user', content: '家庭問題' }]
      );

      expect(databaseService.conversation.update).not.toHaveBeenCalled();
      expect(useConversationStore.getState().streamingTitles['conv-malformed']).toBeUndefined();
    });

    it('should parse a title event split across arbitrary network chunks', async () => {
      const encodedEvent = new TextEncoder().encode(
        'data: {"content": "家庭衝突與焦慮"}\n\ndata: [DONE]\n\n'
      );
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encodedEvent.slice(0, 12));
          controller.enqueue(encodedEvent.slice(12, 25));
          controller.enqueue(encodedEvent.slice(25));
          controller.close();
        },
      });
      vi.mocked(global.fetch).mockResolvedValue({ ok: true, body: stream } as any);

      await useConversationStore.getState().generateTitle(
        'conv-split-event',
        [{ role: 'user', content: '家庭問題' }]
      );

      expect(databaseService.conversation.update).toHaveBeenCalledWith('conv-split-event', {
        title: '家庭衝突與焦慮',
      });
    });

    it('should persist complete technical noun phrase titles up to the backend hard limit', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            'data: {"content": "mRNA疫苗運作原理"}\n\n'
          ));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        },
      });
      vi.mocked(global.fetch).mockResolvedValue({ ok: true, body: stream } as any);

      await useConversationStore.getState().generateTitle(
        'conv-technical-title',
        [{ role: 'user', content: 'mRNA疫苗如何抵抗病毒，其過程為何' }]
      );

      expect(databaseService.conversation.update).toHaveBeenCalledWith('conv-technical-title', {
        title: 'mRNA疫苗運作原理',
      });
    });

    it('should persist concise English titles up to the backend English limit', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            'data: {"content": "Bayes Theorem Basics"}\n\n'
          ));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        },
      });
      vi.mocked(global.fetch).mockResolvedValue({ ok: true, body: stream } as any);

      await useConversationStore.getState().generateTitle(
        'conv-english-title',
        [{ role: 'user', content: 'Explain Bayes theorem' }]
      );

      expect(databaseService.conversation.update).toHaveBeenCalledWith('conv-english-title', {
        title: 'Bayes Theorem Basics',
      });
    });
  });
});
