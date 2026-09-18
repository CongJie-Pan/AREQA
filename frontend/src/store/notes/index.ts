/**
 * Notes Store
 * Manages user-saved assistant response notes.
 */

import { create } from 'zustand';
import { getCurrentUserId } from '@/database/db';
import type { Message, Note } from '@/database/schema';
import { databaseService } from '@/services/database';
import { logger } from '@/utils/logger';
import { useChatStore } from '@/store/chat';

interface NotesState {
  notes: Note[];
  loading: boolean;
  error: string | null;
  loadNotes: (userId?: string) => Promise<void>;
  addNoteFromMessage: (message: Message, conversationTitle?: string | null) => Promise<Note>;
  updateNoteMetadata: (id: string, updates: { tags?: string[]; isPinned?: boolean }) => Promise<Note>;
  updateNoteContent: (id: string, content: string) => Promise<Note>;
  syncNoteFromMessage: (message: Message) => Promise<Note | null>;
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
   * Updates a note body and mirrors the edit to the linked assistant message.
   */
  updateNoteContent: async (id: string, content: string) => {
    const { note, sourceMessage } = await databaseService.note.updateContentAndSourceMessage(id, content);
    set((state) => ({
      notes: state.notes
        .map((item) => (item.id === note.id ? note : item))
        .sort((left, right) => right.createdAt.getTime() - left.createdAt.getTime()),
      error: null,
    }));

    if (sourceMessage) {
      useChatStore.getState().updateAssistantMessage(sourceMessage.id, {
        content: sourceMessage.content,
        answerBlocks: undefined,
        streamImageSlots: undefined,
      });
    }

    logger.info('note_content_synced_to_message', {
      component: 'useNotesStore',
      noteId: note.id,
      conversationId: note.conversationId,
      messageId: note.messageId,
      syncedSourceMessage: Boolean(sourceMessage),
    });

    return note;
  },

  /**
   * Mirrors an edited assistant response into its linked note, if one exists.
   */
  syncNoteFromMessage: async (message: Message) => {
    const note = await databaseService.note.syncFromMessage(message);
    if (!note) return null;

    set((state) => ({
      notes: state.notes
        .map((item) => (item.id === note.id ? note : item))
        .sort((left, right) => right.createdAt.getTime() - left.createdAt.getTime()),
      error: null,
    }));

    logger.info('note_content_synced_from_message', {
      component: 'useNotesStore',
      noteId: note.id,
      conversationId: note.conversationId,
      messageId: note.messageId,
    });

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
