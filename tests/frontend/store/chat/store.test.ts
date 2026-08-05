import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from '@/store/chat';

describe('Chat Store', () => {
  beforeEach(() => {
    useChatStore.getState().clearMessages();
    useChatStore.getState().setQuotedText(null);
  });

  it('should initialize with quotedText as null', () => {
    const state = useChatStore.getState();
    expect(state.quotedText).toBeNull();
  });

  it('should update quotedText via setQuotedText', () => {
    const testText = 'test selection';
    useChatStore.getState().setQuotedText(testText);
    
    expect(useChatStore.getState().quotedText).toBe(testText);
    
    useChatStore.getState().setQuotedText(null);
    expect(useChatStore.getState().quotedText).toBeNull();
  });

  it('should insert an assistant placeholder at the requested index', () => {
    const state = useChatStore.getState();
    state.setMessages([
      {
        id: 'user-1',
        userId: 'test-user',
        conversationId: 'conversation-1',
        role: 'user',
        content: 'question',
        createdAt: new Date(),
      },
      {
        id: 'assistant-1',
        userId: 'test-user',
        conversationId: 'conversation-1',
        role: 'assistant',
        content: 'old answer',
        createdAt: new Date(),
      },
      {
        id: 'user-2',
        userId: 'test-user',
        conversationId: 'conversation-1',
        role: 'user',
        content: 'later question',
        createdAt: new Date(),
      },
    ]);

    const placeholderId = state.addAssistantMessageAt('conversation-1', 1);
    const messages = useChatStore.getState().messages;

    expect(messages).toHaveLength(4);
    expect(messages.map((message) => message.id)).toEqual([
      'user-1',
      placeholderId,
      'assistant-1',
      'user-2',
    ]);
    expect(messages[1]).toMatchObject({
      conversationId: 'conversation-1',
      role: 'assistant',
      content: '',
      isStreaming: true,
    });
  });

  it('persists answer blocks when streaming ends', () => {
    const state = useChatStore.getState();
    const messageId = state.addAssistantMessage('conversation-1');
    const blocks = [
      { type: 'paragraph' as const, text: '第一段' },
      {
        type: 'image_block' as const,
        slotId: 'visual-1',
        topic: 'Forest plot',
        purpose: 'diagram' as const,
        imageUrl: 'https://example.com/forest.png',
        sourceUrl: 'https://example.com/article',
        sourceDomain: 'example.com',
        caption: 'Forest plot example',
        safetyStatus: 'pass' as const,
        matchConfidence: 0.6,
      },
    ];

    state.startStreaming(messageId);
    state.appendContent('第一段');
    state.setAnswerBlocks(blocks);
    state.endStreaming(undefined, blocks);

    const message = useChatStore.getState().messages.find((item) => item.id === messageId);
    expect(message?.answerBlocks).toEqual(blocks);
    expect(useChatStore.getState().currentAnswerBlocks).toEqual([]);
  });
});
