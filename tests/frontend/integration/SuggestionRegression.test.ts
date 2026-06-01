import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createChatStream } from '@/services/chat-stream/client';
import { useChatStore } from '@/store/chat/store';
import { generateUUID } from '@/utils/id';

// Mock the global fetch API to simulate SSE stream
global.fetch = vi.fn();

describe('Suggestion Regression Test', () => {
  beforeEach(() => {
    useChatStore.getState().clearMessages();
    useChatStore.getState().resetStreamingState();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('test_sse_stream_extracts_suggestions_on_done_event', async () => {
    const conversationId = generateUUID();
    const assistantMessageId = useChatStore.getState().addAssistantMessage(conversationId);
    useChatStore.getState().startStreaming(assistantMessageId);

    const mockSuggestions = ["What is the meaning of the Red Chamber?", "Tell me about Lin Daiyu."];
    
    // Simulate the exact chunk sent by the new backend logic
    const sseChunk = `event: done\ndata: {"suggestions": ${JSON.stringify(mockSuggestions)}}\n\n`;
    
    // Create a mock readable stream
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(sseChunk));
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      },
    });

    (global.fetch as any).mockResolvedValue({
      ok: true,
      body: stream,
    });

    const callbacks = {
      onThinkingStart: vi.fn(),
      onThinkingContent: vi.fn(),
      onThinkingEnd: vi.fn(),
      onContent: vi.fn(),
      onCitations: vi.fn(),
      onDone: vi.fn((suggestions) => {
        // This is what the fixed chat service should do
        useChatStore.getState().endStreaming();
        if (suggestions) {
           useChatStore.getState().updateAssistantMessage(assistantMessageId, { suggestions });
        }
      }),
      onError: vi.fn(),
      onSuggestions: vi.fn(),
    };

    await createChatStream([{ role: 'user', content: 'test' }], callbacks);

    const messages = useChatStore.getState().messages;
    const assistantMsg = messages.find(m => m.id === assistantMessageId);

    // Verify the suggestions successfully made it to the store
    expect(assistantMsg?.suggestions).toBeDefined();
    expect(assistantMsg?.suggestions).toEqual(mockSuggestions);
  });
});
