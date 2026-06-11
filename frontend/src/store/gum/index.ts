import { create } from 'zustand';

export interface Proposition {
  id: number;
  text: string;
  confidence: number;
  updated_at: string | null;
}

export interface GumState {
  propositions: Proposition[];
  suggestions: string[];
  loading: boolean;
  fetchMemory: () => Promise<void>;
  fetchSuggestions: () => Promise<void>;
}

export const useGumStore = create<GumState>((set) => ({
  propositions: [],
  suggestions: [],
  loading: false,

  fetchMemory: async () => {
    set({ loading: true });
    try {
      const res = await fetch('http://localhost:8000/api/v1/memory');
      const data = await res.json();
      if (data.propositions) {
        set({ propositions: data.propositions });
      }
    } catch (error) {
      console.error('Failed to fetch memory:', error);
    } finally {
      set({ loading: false });
    }
  },

  fetchSuggestions: async () => {
    set({ loading: true });
    try {
      const res = await fetch('http://localhost:8000/api/v1/suggestions');
      const data = await res.json();
      if (data.suggestions) {
        set({ suggestions: data.suggestions });
      }
    } catch (error) {
      console.error('Failed to fetch suggestions:', error);
    } finally {
      set({ loading: false });
    }
  },
}));
