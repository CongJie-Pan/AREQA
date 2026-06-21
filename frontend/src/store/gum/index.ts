import { create } from 'zustand';

export interface Proposition {
  id: string | number;
  text: string;
  confidence: number;
  updated_at: string | null;
  context_scope?: string;
  event_types?: string[];
  target?: string;
  functional_type_seeds?: string[];
}

export interface GumState {
  propositions: Proposition[];
  suggestions: string[];
  loading: boolean;
  fetchMemory: () => Promise<void>;
  fetchSuggestions: () => Promise<void>;
  deleteMemory: (id: string | number) => Promise<void>;
  deleteMemories: (ids: (string | number)[]) => Promise<void>;
  editMemory: (id: string | number, text: string) => Promise<void>;
}

export const useGumStore = create<GumState>((set) => ({
  propositions: [],
  suggestions: [],
  loading: false,

  fetchMemory: async () => {
    set({ loading: true });
    try {
      const res = await fetch(`http://localhost:8000/api/v1/memory?t=${Date.now()}`, {
        cache: 'no-store',
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      });
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
      const res = await fetch(`http://localhost:8000/api/v1/suggestions?t=${Date.now()}`, {
        cache: 'no-store',
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      });
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

  deleteMemories: async (ids: (string | number)[]) => {
    try {
      await fetch(`http://localhost:8000/api/v1/memory/batch-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      // Remove from local state
      set((state) => ({ propositions: state.propositions.filter(p => !ids.includes(p.id)) }));
    } catch (error) {
      console.error('Failed to batch delete memories:', error);
    }
  },

  deleteMemory: async (id: string | number) => {
    try {
      await fetch(`http://localhost:8000/api/v1/memory/${id}`, { method: 'DELETE' });
      // Remove from local state
      set((state) => ({ propositions: state.propositions.filter(p => p.id !== id) }));
    } catch (error) {
      console.error('Failed to delete memory:', error);
    }
  },

  editMemory: async (id: string | number, text: string) => {
    try {
      await fetch(`http://localhost:8000/api/v1/memory/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      // Update local state
      set((state) => ({
        propositions: state.propositions.map(p => p.id === id ? { ...p, text } : p)
      }));
    } catch (error) {
      console.error('Failed to edit memory:', error);
    }
  },
}));
