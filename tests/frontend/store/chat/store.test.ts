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
});
