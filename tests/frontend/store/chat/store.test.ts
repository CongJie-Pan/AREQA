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
});
