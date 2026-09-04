/**
 * Zustand store for AREQA Live Tutor state.
 *
 * Realtime WebRTC state is intentionally isolated from the chat stream store.
 * Text transcripts are copied into the normal chat store only after the
 * provider emits finalized transcript events.
 */

import { create } from 'zustand';
import type { LiveTutorStore } from './types';

const initialState = {
  isOpen: false,
  status: 'idle' as const,
  isMuted: false,
  userTranscript: '',
  assistantTranscript: '',
  error: null as string | null,
};

export const useLiveTutorStore = create<LiveTutorStore>((set) => ({
  ...initialState,
  open: () => set({ isOpen: true, error: null }),
  close: () => set({ isOpen: false, status: 'idle', isMuted: false, error: null }),
  setStatus: (status) => set({ status }),
  setMuted: (isMuted) => set({ isMuted, status: isMuted ? 'muted' : 'listening' }),
  setUserTranscript: (userTranscript) => set({ userTranscript }),
  setAssistantTranscript: (assistantTranscript) => set({ assistantTranscript }),
  appendAssistantTranscript: (delta) => set((state) => ({
    assistantTranscript: `${state.assistantTranscript}${delta}`,
  })),
  setError: (error) => set({ error, status: error ? 'error' : 'idle' }),
  resetTranscript: () => set({ userTranscript: '', assistantTranscript: '' }),
}));
