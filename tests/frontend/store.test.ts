import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from '../../frontend/src/store/chat/store';

describe('ChatStore Mode Toggles', () => {
  beforeEach(() => {
    // Reset store before each test
    useChatStore.setState({ useRag: false, useWebSearch: false });
  });

  it('should auto-disable useWebSearch when toggling useRag on', () => {
    useChatStore.setState({ useWebSearch: true });
    
    useChatStore.getState().toggleRag();
    
    const state = useChatStore.getState();
    expect(state.useRag).toBe(true);
    expect(state.useWebSearch).toBe(false);
  });

  it('should auto-disable useRag when toggling useWebSearch on', () => {
    useChatStore.setState({ useRag: true });
    
    useChatStore.getState().toggleWebSearch();
    
    const state = useChatStore.getState();
    expect(state.useWebSearch).toBe(true);
    expect(state.useRag).toBe(false);
  });
});
