import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from '../../frontend/src/store/chat/store';

describe('ChatStore Mode Toggles', () => {
  beforeEach(() => {
    // Reset store before each test
    useChatStore.setState({ useRag: false, useWebSearch: false, searchMode: 'never' });
  });

  it('should auto-disable useWebSearch when toggling useRag on', () => {
    useChatStore.setState({ useWebSearch: true, searchMode: 'always' });
    
    useChatStore.getState().toggleRag();
    
    const state = useChatStore.getState();
    expect(state.useRag).toBe(true);
    expect(state.useWebSearch).toBe(false);
    expect(state.searchMode).toBe('never');
  });

  it('should enable web search explicitly and disable RAG', () => {
    useChatStore.setState({ useRag: true });
    
    useChatStore.getState().toggleWebSearch();
    
    const state = useChatStore.getState();
    expect(state.useWebSearch).toBe(true);
    expect(state.searchMode).toBe('always');
    expect(state.useRag).toBe(false);
  });

  it('should toggle web search between always and never only', () => {
    const store = useChatStore.getState();
    store.toggleWebSearch();
    expect(useChatStore.getState().searchMode).toBe('always');
    useChatStore.getState().toggleWebSearch();
    expect(useChatStore.getState().searchMode).toBe('never');
    expect(useChatStore.getState().useWebSearch).toBe(false);
    useChatStore.getState().toggleWebSearch();
    expect(useChatStore.getState().searchMode).toBe('always');
  });
});
