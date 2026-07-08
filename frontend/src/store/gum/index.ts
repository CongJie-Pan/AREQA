import { create } from 'zustand';
import { getAuthToken } from '@/database/db';

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

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
  summary: { sentence1: string; sentence2: string; hashtags: string[] } | null;
  loading: boolean;
  loadingSummary: boolean;
  fetchMemory: () => Promise<void>;
  fetchSuggestions: () => Promise<void>;
  fetchSummary: () => Promise<void>;
  deleteMemory: (id: string | number) => Promise<void>;
  deleteMemories: (ids: (string | number)[]) => Promise<void>;
  editMemory: (id: string | number, text: string) => Promise<void>;
}

export const useGumStore = create<GumState>((set) => ({
  propositions: [],
  suggestions: [],
  summary: null,
  loading: false,
  loadingSummary: false,

  fetchMemory: async () => {
    set({ loading: true });
    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${backendUrl}/api/v1/memory?t=${Date.now()}`, {
        cache: 'no-store',
        headers
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

  fetchSummary: async () => {
    set({ loadingSummary: true });
    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${backendUrl}/api/v1/memory/summary?t=${Date.now()}`, {
        cache: 'no-store',
        headers
      });
      const data = await res.json();
      if (data.summary) {
        set({ summary: data.summary });
      }
    } catch (error) {
      console.error('Failed to fetch summary:', error);
    } finally {
      set({ loadingSummary: false });
    }
  },

  fetchSuggestions: async () => {
    set({ loading: true });
    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${backendUrl}/api/v1/suggestions?t=${Date.now()}`, {
        cache: 'no-store',
        headers
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
      const token = getAuthToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      await fetch(`${backendUrl}/api/v1/memory/batch-delete`, {
        method: 'POST',
        headers,
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
      const token = getAuthToken();
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      await fetch(`${backendUrl}/api/v1/memory/${id}`, { 
        method: 'DELETE',
        headers
      });
      // Remove from local state
      set((state) => ({ propositions: state.propositions.filter(p => p.id !== id) }));
    } catch (error) {
      console.error('Failed to delete memory:', error);
    }
  },

  editMemory: async (id: string | number, text: string) => {
    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      await fetch(`${backendUrl}/api/v1/memory/${id}`, {
        method: 'PUT',
        headers,
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
