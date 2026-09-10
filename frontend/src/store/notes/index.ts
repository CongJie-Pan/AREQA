/**
 * Notes Store
 * Manages user-saved assistant response notes.
 */

import { create } from 'zustand';
import { getCurrentUserId } from '@/database/db';
import type { Message, Note } from '@/database/schema';
import { databaseService } from '@/services/database';
import { logger } from '@/utils/logger';

interface NotesState {
  notes: Note[];
  loading: boolean;
  error: string | null;
  loadNotes: (userId?: string) => Promise<void>;
  addNoteFromMessage: (message: Message, conversationTitle?: string | null) => Promise<Note>;
  updateNoteMetadata: (id: string, updates: { tags?: string[]; isPinned?: boolean }) => Promise<Note>;
  deleteNote: (id: string) => Promise<void>;
  isMessageSaved: (messageId: string) => boolean;
}

export const useNotesStore = create<NotesState>((set, get) => ({
  notes: [],
  loading: false,
  error: null,

  /**
   * Loads notes for the current or provided user.
   */
  loadNotes: async (overrideUserId?: string) => {
    const userId = overrideUserId || getCurrentUserId();
    if (!userId) {
      set({ notes: [], loading: false, error: null });
      return;
    }

    set({ loading: true, error: null });
    try {
      const notes = await databaseService.note.getAll(userId);
      set({ notes, loading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logger.error('Load notes error', error instanceof Error ? error : new Error(message), {
        component: 'useNotesStore',
      });
      set({ error: message, loading: false });
    }
  },

  /**
   * Saves an assistant message as a note and refreshes local note state.
   */
  addNoteFromMessage: async (message: Message, conversationTitle?: string | null) => {
    const note = await databaseService.note.addFromMessage(message, conversationTitle);
    set((state) => {
      const exists = state.notes.some((item) => item.id === note.id);
      return {
        notes: exists
          ? state.notes.map((item) => (item.id === note.id ? note : item))
          : [note, ...state.notes],
        error: null,
      };
    });
    return note;
  },

  /**
   * Updates note organization metadata without changing the source snapshot.
   */
  updateNoteMetadata: async (id: string, updates: { tags?: string[]; isPinned?: boolean }) => {
    const note = await databaseService.note.updateMetadata(id, updates);
    set((state) => ({
      notes: state.notes
        .map((item) => (item.id === note.id ? note : item))
        .sort((left, right) => right.createdAt.getTime() - left.createdAt.getTime()),
      error: null,
    }));
    return note;
  },

  /**
   * Deletes one note while preserving the original conversation message.
   */
  deleteNote: async (id: string) => {
    await databaseService.note.delete(id);
    set((state) => ({
      notes: state.notes.filter((note) => note.id !== id),
      error: null,
    }));
  },

  /**
   * Reads whether a source assistant message is already saved in state.
   */
  isMessageSaved: (messageId: string) => get().notes.some((note) => note.messageId === messageId),
}));
