/**
 * Chat Store Type Definitions
 * Types for managing chat state with Zustand
 */

import type { AnswerBlock, AttachmentMetadata, Message, MessageFeedback, MessageFeedbackDetails } from '@/database/schema';
import type { CitationSource } from '@/components/Citations';

export type SearchMode = 'auto' | 'always' | 'never';
export type TutorProfile = 'general' | 'english';

/** Privacy-safe location of an image marker in the live public answer. */
export interface StreamingImageSlot {
  /** Stable identifier shared with the final ImageBlock. */
  slotId: string;
  /** Zero-based paragraph anchor retained for diagnostics and replay tests. */
  anchorAfterParagraph: number;
  /** UTF-16 code-unit offset used by JavaScript String.slice. */
  contentOffset: number;
}

/**
 * Display message for UI rendering
 * Extends database Message with streaming state
 */
export interface DisplayMessage extends Message {
  /** Ephemeral sentence captions released at playback start, never persisted. */
  voiceCaption?: string;
  /** Transient caption timing, never stored as conversation content. */
  voicePlayback?: 'waiting' | 'playing' | 'finished' | 'interrupted';
  /** Whether this message is currently being streamed */
  isStreaming?: boolean;
  /** Suggested follow-up questions */
  suggestions?: string[];
  /** Transient marker positions used only by the mounted live renderer. */
  streamImageSlots?: StreamingImageSlot[];
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
  /** Transient image jobs, isolated from text and voice streaming state. */
  imageGenerationRequests: Record<string, {
    userId: string;
    conversationId: string | null;
    assistantMessageId: string | null;
  }>;
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
  /** Structured display blocks from the current response stream. */
  currentAnswerBlocks: AnswerBlock[];

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
  /** Whether explicitly requesting Web Search API */
  useWebSearch: boolean;
  /** Web search policy for the current request. */
  searchMode: SearchMode;
  /** Whether explicitly forcing the model to wrap reasoning in <think> */
  forceThink: boolean;
  /** Optional subject tutor profile selected for new outgoing turns. */
  tutorProfile: TutorProfile;

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
  addUserMessage: (content: string, conversationId: string, attachments?: AttachmentMetadata[]) => string;
  /** Add an assistant message (usually empty, to be filled by streaming) */
  addAssistantMessage: (conversationId: string) => string;
  /** Insert an assistant message at a specific position in the conversation */
  addAssistantMessageAt: (conversationId: string, index: number) => string;
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
  /** Update assistant feedback by message ID */
  setMessageFeedback: (id: string, feedback: MessageFeedback | null, details?: MessageFeedbackDetails) => void;

  // Streaming processing
  /** Start streaming for a message */
  startStreaming: (messageId: string) => void;
  /** Append content to thinking */
  appendThinkingContent: (content: string) => void;
  /** End thinking phase */
  endThinking: () => void;
  /** Append content to answer */
  appendContent: (content: string) => void;
  /** End streaming and finalize message; pass final payloads to avoid race conditions */
  endStreaming: (finalSources?: CitationSource[], finalAnswerBlocks?: AnswerBlock[]) => void;

  // Citations
  /** Set citation URLs */
  setCitations: (citations: string[]) => void;
  /** Set structured illustrated answer blocks */
  setAnswerBlocks: (blocks: AnswerBlock[]) => void;
  /** Record one image marker without exposing its private retrieval metadata. */
  addImageSlot: (slot: StreamingImageSlot) => void;

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
  /** Toggle Web Search mode */
  toggleWebSearch: () => void;
  /** Toggle Think mode */
  toggleThink: () => void;
  /** Select the subject tutor profile for new outgoing turns. */
  setTutorProfile: (profile: TutorProfile) => void;

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
