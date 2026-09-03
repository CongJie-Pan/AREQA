/**
 * Chat Store
 * Zustand store for managing chat state and streaming
 *
 * Note: All state updates use atomic operations to prevent race conditions
 * when multiple chunks arrive in rapid succession during streaming.
 */

import { create } from 'zustand';
import { getCurrentUserId } from '@/database/db';
import { generateUUID } from '@/utils/id';
import type { ChatStore, DisplayMessage } from './types';
import type { CitationSource } from '@/components/Citations';
import type { AnswerBlock, AttachmentMetadata, MessageFeedback, MessageFeedbackDetails } from '@/database/schema';

const STREAM_IMAGE_SLOT_ID_PATTERN = /^[A-Za-z0-9_-]{1,40}$/;
const MAX_STREAM_IMAGE_SLOTS = 4;

/**
 * RAG statuses that are allowed to keep the frontend waiting panel visible.
 *
 * Backend status codes remain richer than the chat UI because they are useful
 * for tracing and server-side orchestration. The UI intentionally exposes only
 * the learner-facing waiting states; once thinking or answer generation starts,
 * these visible statuses must not reappear from late SSE telemetry.
 */
const FRONTEND_VISIBLE_RAG_STATUSES: ReadonlySet<ChatStore['ragStatus']> = new Set([
  'routing',
  'searching_dense',
]);

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
  currentAnswerBlocks: [] as AnswerBlock[],
  quotedText: null as string | null,
  error: null as Error | null,
  tokenUsage: null as { promptTokens?: number; completionTokens?: number; totalTokens?: number } | null,
  useRag: false,
  useWebSearch: false,
  searchMode: 'auto' as const,
  forceThink: true,
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
  addUserMessage: (content: string, conversationId: string, attachments: AttachmentMetadata[] = []) => {
    const id = generateUUID();
    const message: DisplayMessage = {
      id,
      userId: getCurrentUserId() ?? 'guest',
      conversationId,
      role: 'user',
      content,
      ...(attachments.length > 0 ? { attachments } : {}),
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
      userId: getCurrentUserId() ?? 'guest',
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

  addAssistantMessageAt: (conversationId: string, index: number) => {
    const id = generateUUID();
    const message: DisplayMessage = {
      id,
      userId: getCurrentUserId() ?? 'guest',
      conversationId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
      isStreaming: true,
    };

    set((state) => {
      const insertionIndex = Math.max(0, Math.min(index, state.messages.length));
      return {
        messages: [
          ...state.messages.slice(0, insertionIndex),
          message,
          ...state.messages.slice(insertionIndex),
        ],
      };
    });

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

  setMessageFeedback: (
    id: string,
    feedback: MessageFeedback | null,
    details: MessageFeedbackDetails = {}
  ) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id
          ? {
              ...msg,
              feedback,
              feedbackReason: feedback === 'disliked' ? details.reason ?? null : null,
              feedbackComment: feedback === 'disliked' ? details.comment ?? null : null,
              feedbackUpdatedAt: feedback ? new Date() : null,
            }
          : msg
      ),
    }));
  },

  // Streaming processing
  startStreaming: (messageId: string) => {
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === messageId ? { ...message, streamImageSlots: [] } : message
      ),
      isStreaming: true,
      currentStreamingId: messageId,
      thinkingContent: '',
      thinkingStartTime: null,
      isThinking: false,
      currentContent: '',
      currentCitations: [],
      currentAnswerBlocks: [],
      error: null,
      tokenUsage: null,
      ragStatus: 'idle',
      ragMessage: '',
      ragSources: [],
    }));
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
        // Hide the pre-generation RAG panel as soon as private reasoning starts.
        // Some streams never emit a dedicated `generating` status before tokens.
        ragStatus: 'generating',
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
        // Public answer tokens are the strongest frontend signal that the
        // status panel should be gone, regardless of late backend telemetry.
        ragStatus: 'generating',
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
   * End streaming and finalize the message.
   *
   * Accepts optional final payloads to avoid races where metadata SSE events
   * have not committed to Zustand before the terminal event is processed.
   */
  endStreaming: (finalSources?: CitationSource[], finalAnswerBlocks?: AnswerBlock[]) => {
    set((state) => {
      // Prefer explicitly passed sources (from local closure) over state.ragSources
      // to avoid the race condition on cold-start / fast SSE delivery.
      const sourcesToPersist = finalSources ?? (state.ragSources.length > 0 ? state.ragSources : undefined);
      const answerBlocksToPersist = finalAnswerBlocks ?? (
        state.currentAnswerBlocks.length > 0 ? state.currentAnswerBlocks : undefined
      );

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
                  sources: sourcesToPersist,
                  answerBlocks: answerBlocksToPersist,
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
          currentAnswerBlocks: [],
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
   * Set structured illustrated answer blocks for the streaming assistant reply.
   *
   * The backend owns image verification. The store only mirrors the payload
   * onto the current message so rendering remains live during streaming.
   */
  setAnswerBlocks: (blocks: AnswerBlock[]) => {
    set((state) => ({
      currentAnswerBlocks: blocks,
      messages: state.currentStreamingId
        ? state.messages.map((msg) =>
            msg.id === state.currentStreamingId ? { ...msg, answerBlocks: blocks } : msg
          )
        : state.messages,
    }));
  },

  /**
   * Record a live image marker exactly once.
   *
   * Args:
   *   slot: Privacy-safe marker position validated at the SSE boundary.
   *
   * Side Effects:
   *   Atomically updates only the active streaming message. Invalid, duplicate,
   *   or excess slots are ignored without changing state.
   *
   * The backend already bounds markers to four per answer. The store repeats
   * that boundary and validates offsets because SSE payloads are untrusted at
   * the browser boundary. Raw marker queries and captions never reach state.
   */
  addImageSlot: (slot) => {
    if (
      !STREAM_IMAGE_SLOT_ID_PATTERN.test(slot.slotId) ||
      !Number.isSafeInteger(slot.contentOffset) ||
      slot.contentOffset < 0 ||
      !Number.isSafeInteger(slot.anchorAfterParagraph) ||
      slot.anchorAfterParagraph < 0
    ) {
      return;
    }

    set((state) => ({
      messages: state.currentStreamingId
        ? state.messages.map((message) => {
            if (message.id !== state.currentStreamingId) return message;
            const slots = message.streamImageSlots ?? [];
            if (
              slots.some((item) => item.slotId === slot.slotId) ||
              slots.length >= MAX_STREAM_IMAGE_SLOTS
            ) {
              return message;
            }
            return { ...message, streamImageSlots: [...slots, slot] };
          })
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
      currentAnswerBlocks: [],
      quotedText: null,
      error: null,
      ragStatus: 'idle',
      ragMessage: '',
      ragSources: [],
    });
  },

  // Toggles
  toggleRag: () => set((state) => ({ 
    useRag: !state.useRag,
    useWebSearch: false,
    searchMode: state.useRag ? state.searchMode : 'never'
  })),
  toggleWebSearch: () => set((state) => {
    const searchMode = state.searchMode === 'auto'
      ? 'always'
      : state.searchMode === 'always' ? 'never' : 'auto';
    return {
      searchMode,
      useWebSearch: searchMode === 'always',
      useRag: false,
    };
  }),
  toggleThink: () => set((state) => ({ forceThink: !state.forceThink })),

  // RAG Visualization
  setRagStatus: (status, message) => set((state) => {
    // SSE action/status events can arrive after generation has started. Keep
    // backend-only state for persistence, but prevent visible waiting states
    // such as `routing` from resurrecting the panel over active output.
    const hasGenerationStarted = state.isThinking
      || state.thinkingContent.length > 0
      || state.currentContent.length > 0;
    const nextStatus = hasGenerationStarted && FRONTEND_VISIBLE_RAG_STATUSES.has(status)
      ? 'generating'
      : status;

    return {
      ragStatus: nextStatus,
      ...(message !== undefined ? { ragMessage: message } : {}),
    };
  }),
  setRagSources: (sources) => set({ ragSources: sources }),
}));
