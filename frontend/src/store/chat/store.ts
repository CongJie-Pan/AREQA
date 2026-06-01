/**
 * Chat Store
 * Zustand store for managing chat state and streaming
 *
 * Note: All state updates use atomic operations to prevent race conditions
 * when multiple chunks arrive in rapid succession during streaming.
 */

import { create } from 'zustand';
import { generateUUID } from '@/utils/id';
import type { ChatStore, DisplayMessage } from './types';
import type { CitationSource } from '@/components/Citations';

/**
 * Initial state for the chat store
 */
const initialState = {
  messages: [] as DisplayMessage[],
  isStreaming: false,
  currentStreamingId: null as string | null,
  thinkingContent: '',
  thinkingStartTime: null as number | null,
  isThinking: false,
  currentContent: '',
  currentCitations: [] as string[],
  quotedText: null as string | null,
  error: null as Error | null,
  tokenUsage: null as { promptTokens?: number; completionTokens?: number; totalTokens?: number } | null,
  useRag: false,
  forceThink: false,
  ragStatus: 'idle' as 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done',
  ragMessage: '',
  ragSources: [] as CitationSource[],
};

/**
 * Chat store for managing conversation messages and streaming state
 *
 * Design decisions:
 * - All streaming updates use atomic set() with function to avoid race conditions
 * - State is updated in-place with the streaming message to enable real-time UI updates
 * - Thinking state tracks both content and timing for duration display
 */
export const useChatStore = create<ChatStore>((set) => ({
  ...initialState,

  // Message operations
  addUserMessage: (content: string, conversationId: string) => {
    const id = generateUUID();
    const message: DisplayMessage = {
      id,
      conversationId,
      role: 'user',
      content,
      createdAt: new Date(),
    };

    set((state) => ({
      messages: [...state.messages, message],
    }));

    return id;
  },

  addAssistantMessage: (conversationId: string) => {
    const id = generateUUID();
    const message: DisplayMessage = {
      id,
      conversationId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
      isStreaming: true,
    };

    set((state) => ({
      messages: [...state.messages, message],
    }));

    return id;
  },

  updateAssistantMessage: (id: string, updates: Partial<DisplayMessage>) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    }));
  },

  setMessages: (messages: DisplayMessage[]) => {
    set({ messages });
  },

  clearMessages: () => {
    set({ messages: [] });
  },

  removeMessage: (id: string) => {
    set((state) => ({
      messages: state.messages.filter((msg) => msg.id !== id),
    }));
  },

  updateMessageContent: (id: string, content: string) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, content } : msg
      ),
    }));
  },

  // Streaming processing
  startStreaming: (messageId: string) => {
    set({
      isStreaming: true,
      currentStreamingId: messageId,
      thinkingContent: '',
      thinkingStartTime: null,
      isThinking: false,
      currentContent: '',
      currentCitations: [],
      error: null,
      tokenUsage: null,
      ragStatus: 'idle',
      ragMessage: '',
      ragSources: [],
    });
  },

  /**
   * Append thinking content during streaming
   * Uses atomic update to prevent race conditions with rapid chunk arrivals
   */
  appendThinkingContent: (content: string) => {
    set((state) => {
      // If this is the first thinking content, record start time
      const thinkingStartTime = state.thinkingStartTime ?? Date.now();

      return {
        thinkingContent: state.thinkingContent + content,
        thinkingStartTime,
        isThinking: true,
      };
    });
  },

  /**
   * End thinking phase and update the message with reasoning content
   * Uses atomic update to ensure consistent state
   */
  endThinking: () => {
    set((state) => {
      const thinkingDuration = state.thinkingStartTime
        ? Date.now() - state.thinkingStartTime
        : undefined;

      // If we have a streaming message, update it with thinking content
      if (state.currentStreamingId) {
        return {
          messages: state.messages.map((msg) =>
            msg.id === state.currentStreamingId
              ? {
                  ...msg,
                  reasoning: {
                    content: state.thinkingContent,
                    duration: thinkingDuration,
                  },
                }
              : msg
          ),
          isThinking: false,
        };
      }

      return { isThinking: false };
    });
  },

  /**
   * Append content during streaming
   * Uses single atomic update to prevent race conditions
   */
  appendContent: (content: string) => {
    set((state) => {
      const newContent = state.currentContent + content;

      // Update both the local tracking and the message in a single atomic operation
      return {
        currentContent: newContent,
        messages: state.currentStreamingId
          ? state.messages.map((msg) =>
              msg.id === state.currentStreamingId
                ? { ...msg, content: newContent }
                : msg
            )
          : state.messages,
      };
    });
  },

  /**
   * End streaming and finalize the message
   */
  endStreaming: () => {
    set((state) => {
      // Finalize the streaming message if we have one
      if (state.currentStreamingId) {
        return {
          messages: state.messages.map((msg) =>
            msg.id === state.currentStreamingId
              ? {
                  ...msg,
                  content: state.currentContent,
                  citations:
                    state.currentCitations.length > 0
                      ? state.currentCitations
                      : undefined,
                  // Persist structured RAG sources onto the message so the
                  // Citations panel survives after streaming ends
                  sources:
                    state.ragSources.length > 0
                      ? state.ragSources
                      : undefined,
                  isStreaming: false,
                }
              : msg
          ),
          isStreaming: false,
          currentStreamingId: null,
          // Reset RAG transient state after persisting to message
          ragStatus: 'idle' as const,
          ragMessage: '',
          ragSources: [],
        };
      }

      return {
        isStreaming: false,
        currentStreamingId: null,
      };
    });
  },

  /**
   * Set citations for the current message
   * Uses atomic update to keep state consistent
   */
  setCitations: (citations: string[]) => {
    set((state) => ({
      currentCitations: citations,
      messages: state.currentStreamingId
        ? state.messages.map((msg) =>
            msg.id === state.currentStreamingId ? { ...msg, citations } : msg
          )
        : state.messages,
    }));
  },

  /**
   * Set text to be quoted in next message
   */
  setQuotedText: (text: string | null) => {
    set({ quotedText: text });
  },

  // Error handling
  setError: (error: Error | null) => {
    set({ error, isStreaming: false });
  },

  // Metadata
  setTokenUsage: (usage) => {
    set({ tokenUsage: usage });
  },

  // Reset
  restoreStreamingState: (partialState) => {
    set((state) => ({ ...state, ...partialState }));
  },

  resetStreamingState: () => {
    set({
      isStreaming: false,
      currentStreamingId: null,
      thinkingContent: '',
      thinkingStartTime: null,
      isThinking: false,
      currentContent: '',
      currentCitations: [],
      quotedText: null,
      error: null,
      ragStatus: 'idle',
      ragMessage: '',
      ragSources: [],
    });
  },

  // Toggles
  toggleRag: () => set((state) => ({ useRag: !state.useRag })),
  toggleThink: () => set((state) => ({ forceThink: !state.forceThink })),

  // RAG Visualization
  setRagStatus: (status, message) => set({ 
    ragStatus: status, 
    ...(message !== undefined ? { ragMessage: message } : {}) 
  }),
  setRagSources: (sources) => set({ ragSources: sources }),
}));
