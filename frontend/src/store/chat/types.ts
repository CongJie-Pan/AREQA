/**
 * Chat Store Type Definitions
 * Types for managing chat state with Zustand
 */

import type { Message } from '@/database/schema';
import type { CitationSource } from '@/components/Citations';

/**
 * Display message for UI rendering
 * Extends database Message with streaming state
 */
export interface DisplayMessage extends Message {
  /** Whether this message is currently being streamed */
  isStreaming?: boolean;
  /** Suggested follow-up questions */
  suggestions?: string[];
}

/**
 * Thinking state information
 */
export interface ThinkingState {
  /** Accumulated thinking content */
  content: string;
  /** Whether AI is currently in thinking phase */
  isThinking: boolean;
  /** Timestamp when thinking started */
  startTime: number | null;
  /** Calculated duration in milliseconds */
  duration?: number;
}

/**
 * Chat state managed by Zustand
 */
export interface ChatState {
  // Message state
  /** All messages in current conversation */
  messages: DisplayMessage[];

  // Streaming state
  /** Whether currently receiving streamed response */
  isStreaming: boolean;
  /** ID of message currently being streamed */
  currentStreamingId: string | null;

  // Thinking state
  /** Accumulated thinking content */
  thinkingContent: string;
  /** Timestamp when thinking started */
  thinkingStartTime: number | null;
  /** Whether AI is in thinking phase */
  isThinking: boolean;

  // Response content
  /** Accumulated answer content */
  currentContent: string;
  /** Citation URLs from response */
  currentCitations: string[];

  // Selection/Quote state
  /** Selected text for quoting in ChatInput */
  quotedText: string | null;

  // Error state
  /** Current error if any */
  error: Error | null;

  // Usage info
  /** Token usage from the backend */
  tokenUsage: { promptTokens?: number; completionTokens?: number; totalTokens?: number } | null;

  // Toggle modes
  /** Whether explicitly requesting RAG contextual augmentation */
  useRag: boolean;
  /** Whether explicitly forcing the model to wrap reasoning in <think> */
  forceThink: boolean;

  // RAG Visualization State
  /** Current phase of the RAG retrieval pipeline */
  ragStatus: 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done';
  /** RAG domain-specific status message */
  ragMessage: string;
  /** Detailed RAG sources payload containing snippets and scores */
  ragSources: CitationSource[];
}

/**
 * Chat actions for store manipulation
 */
export interface ChatActions {
  // Message operations
  /** Add a user message to the conversation */
  addUserMessage: (content: string, conversationId: string) => string;
  /** Add an assistant message (usually empty, to be filled by streaming) */
  addAssistantMessage: (conversationId: string) => string;
  /** Update an existing assistant message */
  updateAssistantMessage: (id: string, updates: Partial<DisplayMessage>) => void;
  /** Set all messages (when loading from database) */
  setMessages: (messages: DisplayMessage[]) => void;
  /** Clear all messages */
  clearMessages: () => void;
  /** Remove a specific message by ID */
  removeMessage: (id: string) => void;
  /** Update message content by ID */
  updateMessageContent: (id: string, content: string) => void;

  // Streaming processing
  /** Start streaming for a message */
  startStreaming: (messageId: string) => void;
  /** Append content to thinking */
  appendThinkingContent: (content: string) => void;
  /** End thinking phase */
  endThinking: () => void;
  /** Append content to answer */
  appendContent: (content: string) => void;
  /** End streaming and finalize message */
  endStreaming: () => void;

  // Citations
  /** Set citation URLs */
  setCitations: (citations: string[]) => void;

  // Selection/Quote actions
  /** Set text to be quoted in next message */
  setQuotedText: (text: string | null) => void;

  // Error handling
  /** Set error state */
  setError: (error: Error | null) => void;

  // Metadata
  /** Set token usage metrics */
  setTokenUsage: (usage: { promptTokens?: number; completionTokens?: number; totalTokens?: number }) => void;

  // Reset
  /** Reset all streaming state */
  resetStreamingState: () => void;

  /** Restore streaming state when switching back to an active stream */
  restoreStreamingState: (state: Partial<ChatState>) => void;

  // Mode Toggles
  /** Toggle RAG mode */
  toggleRag: () => void;
  /** Toggle Think mode */
  toggleThink: () => void;

  // RAG Visualization
  /** Set the RAG retrieval status and message */
  setRagStatus: (status: 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done', message?: string) => void;
  /** Set structured RAG sources */
  setRagSources: (sources: CitationSource[]) => void;
}

/**
 * Combined Chat Store type
 */
export type ChatStore = ChatState & ChatActions;
