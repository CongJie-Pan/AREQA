/**
 * Conversation Store
 * Zustand store for managing conversation list and selection
 */

import { create } from 'zustand';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import type { Conversation, ConversationKind } from '@/database/schema';
import { conversationKindOf, normalizeConversationKind } from '@/utils/conversationKind';
import type { ConversationStore } from './types';
import { logger } from '@/utils/logger';

const GENERATED_TITLE_MAX_LENGTH = 18;
const GENERATED_ENGLISH_TITLE_MAX_LENGTH = 48;
const CONVERSATION_LOAD_TIMEOUT_MS = 7000;
let conversationLoadSequence = 0;
const WORKSPACE_STORAGE_KEY = 'areqa:workspace';

/** Read the remembered workspace; storage is a convenience, so any failure means chat. */
export function readStoredWorkspace(): ConversationKind {
  try {
    if (typeof window === 'undefined') return 'chat';
    return normalizeConversationKind(window.localStorage.getItem(WORKSPACE_STORAGE_KEY));
  } catch {
    return 'chat';
  }
}

function storeWorkspace(workspace: ConversationKind): void {
  try {
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, workspace);
  } catch {
    // Remembering the workspace is optional; chat keeps working without storage.
  }
}

function withTimeout<T>(operation: PromiseLike<T>, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = globalThis.setTimeout(() => {
      reject(new Error(`${label} timed out`));
    }, CONVERSATION_LOAD_TIMEOUT_MS);

    Promise.resolve(operation)
      .then(resolve, reject)
      .finally(() => {
        globalThis.clearTimeout(timeoutId);
      });
  });
}

function isEnglishLikeTitle(title: string): boolean {
  const latinCount = (title.match(/[A-Za-z]/g) || []).length;
  const cjkCount = (title.match(/[\u3400-\u9fff]/g) || []).length;
  return latinCount >= 4 && latinCount >= Math.max(cjkCount * 2, 1);
}

const isValidGeneratedTitle = (title: string): boolean => {
  const normalized = title.trim();
  const maxLength = isEnglishLikeTitle(normalized)
    ? GENERATED_ENGLISH_TITLE_MAX_LENGTH
    : GENERATED_TITLE_MAX_LENGTH;
  return (
    normalized.length > 0 &&
    Array.from(normalized).length <= maxLength &&
    !/[\n\r#*`]|(?:對話)?標題\s*[:：]|title\s*[:：]|請根據|上述對話|對話內容|conversation content|generate a title/i.test(normalized)
  );
};

/**
 * Initial state for the conversation store
 */
const initialState = {
  conversations: [] as Conversation[],
  activeConversationId: null as string | null,
  isLoading: false,
  isMessageHandoffLoading: false,
  error: null as Error | null,
  streamingTitles: {} as Record<string, string>,
  workspace: readStoredWorkspace(),
};

/**
 * Conversation store for managing conversation list
 */
export const useConversationStore = create<ConversationStore>((set, get) => ({
  ...initialState,

  loadConversations: async (userId: string) => {
    const sequence = ++conversationLoadSequence;
    const startedAt = performance.now();
    let retainedCount = 0;
    set((state) => {
      const conversations = state.conversations.filter((conversation) => conversation.userId === userId);
      retainedCount = conversations.length;
      const removedForeignHistory = conversations.length !== state.conversations.length;
      return {
        conversations,
        activeConversationId: removedForeignHistory && !conversations.some((conversation) => conversation.id === state.activeConversationId)
          ? null : state.activeConversationId,
        streamingTitles: removedForeignHistory ? {} : state.streamingTitles,
        isLoading: true,
        error: null,
      };
    });
    logger.info('chat_history_reload_started', {
      component: 'useConversationStore', sequence,
      mode: retainedCount > 0 ? 'refresh' : 'initial', retainedCount,
    });
    try {
      const conversations = await withTimeout(
        databaseService.conversation.getAll(userId),
        'Conversation history load',
      );
      // A later load or account reset owns the state once this request is stale.
      if (sequence !== conversationLoadSequence) {
        logger.info('chat_history_reload_discarded', { component: 'useConversationStore', sequence });
        return;
      }
      set({ conversations, isLoading: false });
      logger.info('chat_history_reload_completed', {
        component: 'useConversationStore', sequence, count: conversations.length,
        durationMs: Math.round(performance.now() - startedAt),
      });
    } catch (error) {
      if (sequence !== conversationLoadSequence) return;
      set({
        error: error instanceof Error ? error : new Error(String(error)),
        isLoading: false,
      });
      logger.info('chat_history_reload_failed', {
        component: 'useConversationStore', sequence, retainedCount,
        durationMs: Math.round(performance.now() - startedAt),
      });
    }
  },

  createConversation: async (title?: string, kind?: ConversationKind) => {
    try {
      const conversation = await databaseService.conversation.create(title, kind ?? 'chat');
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
    // Opening a conversation (sidebar, branch link, search) shows its workspace.
    const conversation = get().conversations.find((item) => item.id === id);
    const workspace = conversation ? conversationKindOf(conversation) : get().workspace;
    if (workspace !== get().workspace) {
      storeWorkspace(workspace);
      logger.info('workspace_followed_conversation', { component: 'useConversationStore', conversationId: id, workspace });
    }
    set({ activeConversationId: id, error: null, workspace });
  },

  setWorkspace: (workspace: ConversationKind) => {
    const next = normalizeConversationKind(workspace);
    if (next === get().workspace) return;
    storeWorkspace(next);
    logger.info('workspace_switched', { component: 'useConversationStore', workspace: next });
    set({ workspace: next });
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

  clearState: () => {
    conversationLoadSequence += 1;
    set({
      conversations: [],
      activeConversationId: null,
      isLoading: false,
      isMessageHandoffLoading: false,
      error: null,
      streamingTitles: {},
    });
  },

  setLoading: (isLoading: boolean) => {
    set({ isLoading });
  },

  setMessageHandoffLoading: (isLoading: boolean) => {
    set({ isMessageHandoffLoading: isLoading });
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
      let sseBuffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        sseBuffer += decoder.decode(value, { stream: true });
        const lines = sseBuffer.split('\n');
        sseBuffer = lines.pop() ?? '';

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

      sseBuffer += decoder.decode();
      if (sseBuffer.trim().startsWith('data: ')) {
        const dataStr = sseBuffer.trim().slice(6);
        if (dataStr !== '[DONE]' && !dataStr.startsWith('[ERROR]')) {
          try {
            const data = JSON.parse(dataStr);
            if (data.content) fullTitle += data.content;
          } catch {
            // An incomplete final SSE event is ignored and never persisted.
          }
        }
      }

      // Persist the final title
      if (isValidGeneratedTitle(fullTitle)) {
        const finalTitle = fullTitle.trim();
        await databaseService.conversation.update(conversationId, { title: finalTitle });
        
        // Refresh conversations to show the persistent title
        const userId = getCurrentUserId();
        if (userId) {
          const conversations = await databaseService.conversation.getAll(userId);
          set({ conversations });
        }
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
