import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useGumStore } from '../../../../frontend/src/store/gum';

// Mock global fetch
global.fetch = vi.fn();

describe('useGumStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGumStore.setState({
      propositions: [],
      suggestions: [],
      loading: false,
      error: null,
    });
  });

  it('should have correct initial state', () => {
    const state = useGumStore.getState();
    expect(state.propositions).toEqual([]);
    expect(state.suggestions).toEqual([]);
    expect(state.loading).toBe(false);
  });

  it('fetchMemory should fetch memory from API and update state', async () => {
    const mockMemory = [{ content: 'test memory' }];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ propositions: mockMemory }),
    });

    await useGumStore.getState().fetchMemory();

    const state = useGumStore.getState();
    expect(state.propositions).toEqual(mockMemory);
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/memory');
  });

  it('fetchSuggestions should fetch suggestions from API and update state', async () => {
    const mockSuggestions = [{ topic: 'test suggestion' }];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ suggestions: mockSuggestions }),
    });

    await useGumStore.getState().fetchSuggestions();

    const state = useGumStore.getState();
    expect(state.suggestions).toEqual(mockSuggestions);
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/suggestions');
  });
});
