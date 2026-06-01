/**
 * Conversation Store
 * Zustand store for managing conversation list and selection
 */

import { create } from 'zustand';
import { databaseService } from '@/services/database';
import type { Conversation } from '@/database/schema';
import type { ConversationStore } from './types';

/**
 * Initial state for the conversation store
 */
const initialState = {
  conversations: [] as Conversation[],
  activeConversationId: null as string | null,
  isLoading: false,
  error: null as Error | null,
  streamingTitles: {} as Record<string, string>,
};

/**
 * Conversation store for managing conversation list
 */
export const useConversationStore = create<ConversationStore>((set) => ({
  ...initialState,

  loadConversations: async () => {
    set({ isLoading: true, error: null });
    try {
      const conversations = await databaseService.conversation.getAll();
      set({ conversations, isLoading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error : new Error(String(error)),
        isLoading: false,
      });
    }
  },

  createConversation: async (title?: string) => {
    try {
      const conversation = await databaseService.conversation.create(title);
      set((state) => ({
        conversations: [conversation, ...state.conversations],
        activeConversationId: conversation.id,
        error: null,
      }));
      return conversation.id;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      set({ error: err });
      throw err;
    }
  },

  selectConversation: (id: string) => {
    set({ activeConversationId: id, error: null });
  },

  deleteConversation: async (id: string) => {
    try {
      await databaseService.conversation.delete(id);
      set((state) => ({
        conversations: state.conversations.filter((c) => c.id !== id),
        activeConversationId:
          state.activeConversationId === id ? null : state.activeConversationId,
        error: null,
      }));
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      set({ error: err });
      throw err;
    }
  },

  updateConversation: (id: string, updates: Partial<Conversation>) => {
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, ...updates } : c
      ),
    }));
  },

  clearActiveConversation: () => {
    set({ activeConversationId: null });
  },

  setError: (error: Error | null) => {
    set({ error });
  },

  generateTitle: async (conversationId: string, messages: { role: string; content: string }[]) => {
    try {
      // Start streaming state
      set((state) => ({
        streamingTitles: { ...state.streamingTitles, [conversationId]: '' },
      }));

      const response = await fetch('/api/title', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ messages }),
      });

      if (!response.ok || !response.body) {
        throw new Error('Failed to generate title');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullTitle = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.trim().startsWith('data: ')) {
            const dataStr = line.trim().slice(6);
            if (dataStr === '[DONE]') continue;
            if (dataStr.startsWith('[ERROR]')) continue;
            
            try {
              const data = JSON.parse(dataStr);
              if (data.content) {
                fullTitle += data.content;
                set((state) => ({
                  streamingTitles: {
                    ...state.streamingTitles,
                    [conversationId]: fullTitle,
                  },
                }));
              }
            } catch (error) {
              // Ignore parse errors for incomplete chunks
              void error;
            }
          }
        }
      }

      // Persist the final title
      if (fullTitle.trim()) {
        const finalTitle = fullTitle.trim();
        await databaseService.conversation.update(conversationId, { title: finalTitle });
        
        // Refresh conversations to show the persistent title
        const conversations = await databaseService.conversation.getAll();
        set({ conversations });
      }

      // Cleanup
      set((state) => {
        const newStreamingTitles = { ...state.streamingTitles };
        delete newStreamingTitles[conversationId];
        return { streamingTitles: newStreamingTitles };
      });
    } catch (error) {
      console.error('Error generating title:', error);
      set((state) => {
        const newStreamingTitles = { ...state.streamingTitles };
        delete newStreamingTitles[conversationId];
        return { streamingTitles: newStreamingTitles };
      });
    }
  },
}));

/**
 * Selectors for conversation store
 */
export const conversationSelectors = {
  /** Get active conversation */
  activeConversation: (state: ConversationStore): Conversation | undefined => {
    if (!state.activeConversationId) return undefined;
    return state.conversations.find((c) => c.id === state.activeConversationId);
  },

  /** Check if has conversations */
  hasConversations: (state: ConversationStore): boolean => {
    return state.conversations.length > 0;
  },

  /** Get conversation count */
  conversationCount: (state: ConversationStore): number => {
    return state.conversations.length;
  },
};

/**
 * Hook-friendly selector creators
 */
export const selectConversations = (state: ConversationStore) => state.conversations;
export const selectActiveConversationId = (state: ConversationStore) => state.activeConversationId;
export const selectIsLoading = (state: ConversationStore) => state.isLoading;
export const selectError = (state: ConversationStore) => state.error;
