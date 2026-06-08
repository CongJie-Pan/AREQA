import { create } from 'zustand';
import axios from 'axios';

const API_BASE = '/api';

export interface Proposition {
  id: number;
  text: string;
  reasoning: string;
  confidence: number;
  created_at: string;
}

export interface Suggestion {
  id: string;
  title: string;
  description: string;
  benefit: number;
  confidence: number;
}

interface GumboState {
  isRecording: boolean;
  propositions: Proposition[];
  suggestions: Suggestion[];
  userName: string;
  modelName: string;
  llmApiKey: string;
  enableScreenCapture: boolean;
  currentPage: 'suggestions' | 'memory' | 'settings';
  loading: boolean;
  error: string | null;

  setCurrentPage: (page: 'suggestions' | 'memory' | 'settings') => void;
  fetchStatus: () => Promise<void>;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<void>;
  fetchMemory: () => Promise<void>;
  updateMemory: (id: number, text: string, confidence: number) => Promise<void>;
  deleteMemory: (id: number) => Promise<void>;
  fetchSuggestions: () => Promise<void>;
  submitFeedback: (suggestionId: string, isPositive: boolean, textFeedback?: string) => Promise<void>;
  saveSettings: (userName: string, llmApiKey: string, enableScreenCapture: boolean, modelName: string) => Promise<void>;
}

export const useStore = create<GumboState>((set) => ({
  isRecording: false,
  propositions: [],
  suggestions: [],
  userName: 'default_user',
  modelName: 'qwen/qwen3-235b-a22b-2507',
  llmApiKey: '',
  enableScreenCapture: false,
  currentPage: 'suggestions',
  loading: false,
  error: null,

  setCurrentPage: (page) => set({ currentPage: page }),

  fetchStatus: async () => {
    try {
      const res = await axios.get(`${API_BASE}/recording/status`);
      set({
        isRecording: res.data.is_recording,
        userName: res.data.user_name || 'default_user',
        modelName: res.data.model_name || 'gpt-4o-mini'
      });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      console.error('Failed to fetch status:', err);
    }
  },

  startRecording: async () => {
    set({ loading: true, error: null });
    try {
      await axios.post(`${API_BASE}/recording/start`);
      set({ isRecording: true, loading: false });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to start recording', loading: false });
    }
  },

  stopRecording: async () => {
    set({ loading: true, error: null });
    try {
      await axios.post(`${API_BASE}/recording/stop`);
      set({ isRecording: false, loading: false });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to stop recording', loading: false });
    }
  },

  fetchMemory: async () => {
    set({ loading: true, error: null });
    try {
      const res = await axios.get(`${API_BASE}/memory`);
      set({ propositions: res.data.propositions || [], loading: false });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to fetch memory', loading: false });
    }
  },

  updateMemory: async (id, text, confidence) => {
    set({ loading: true, error: null });
    try {
      await axios.put(`${API_BASE}/memory/${id}`, { text, confidence });
      set((state) => ({
        propositions: state.propositions.map((p) =>
          p.id === id ? { ...p, text, confidence } : p
        ),
        loading: false,
      }));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to update proposition', loading: false });
    }
  },

  deleteMemory: async (id) => {
    set({ loading: true, error: null });
    try {
      await axios.delete(`${API_BASE}/memory/${id}`);
      set((state) => ({
        propositions: state.propositions.filter((p) => p.id !== id),
        loading: false,
      }));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to delete proposition', loading: false });
    }
  },

  fetchSuggestions: async () => {
    set({ loading: true, error: null });
    try {
      const res = await axios.get(`${API_BASE}/suggestions`);
      set({ suggestions: res.data.suggestions || [], loading: false });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to fetch suggestions', loading: false });
    }
  },

  submitFeedback: async (suggestionId, isPositive, textFeedback) => {
    try {
      await axios.post(`${API_BASE}/feedback`, {
        suggestion_id: suggestionId,
        is_positive: isPositive,
        text_feedback: textFeedback
      });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      console.error('Failed to submit feedback:', err);
    }
  },

  saveSettings: async (userName, llmApiKey, enableScreenCapture, modelName) => {
    set({ loading: true, error: null });
    try {
      await axios.post(`${API_BASE}/settings`, {
        user_name: userName,
        llm_api_key: llmApiKey,
        enable_screen_capture: enableScreenCapture,
        model_name: modelName
      });
      set({
        userName,
        llmApiKey,
        enableScreenCapture,
        modelName,
        loading: false
      });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to save settings', loading: false });
      throw err;
    }
  }
}));
