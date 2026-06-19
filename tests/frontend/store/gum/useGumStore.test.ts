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
    });
  });

  it('should have correct initial state', () => {
    const state = useGumStore.getState();
    expect(state.propositions).toEqual([]);
    expect(state.suggestions).toEqual([]);
    expect(state.loading).toBe(false);
  });

  it('fetchMemory should fetch memory from API and update state including STITCH tags', async () => {
    const mockMemory = [{ 
      id: 1,
      text: 'test memory', 
      confidence: 0.9,
      updated_at: null,
      context_scope: "Fruit",
      event_types: ["like"],
      target: "apple",
      functional_type_seeds: ["food"]
    }];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ propositions: mockMemory }),
    });

    await useGumStore.getState().fetchMemory();

    const state = useGumStore.getState();
    expect(state.propositions).toEqual(mockMemory);
    
    // Check if the URL matches the timestamped pattern
    const fetchCall = (global.fetch as any).mock.calls[0][0];
    expect(fetchCall).toContain('http://localhost:8000/api/v1/memory?t=');
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
    
    // Check if the URL matches the timestamped pattern
    const fetchCall = (global.fetch as any).mock.calls[0][0];
    expect(fetchCall).toContain('http://localhost:8000/api/v1/suggestions?t=');
  });
});
