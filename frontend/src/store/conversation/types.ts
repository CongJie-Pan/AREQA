/**
 * Conversation Store Type Definitions
 * Types for managing conversation list state with Zustand
 */

import type { Conversation, Message } from '@/database/schema';

/**
 * Conversation state managed by Zustand
 */
export interface ConversationState {
  /** All conversations */
  conversations: Conversation[];
  /** Currently active conversation ID */
  activeConversationId: string | null;
  /** Whether loading conversations */
  isLoading: boolean;
  /** Current error if any */
  error: Error | null;
  /** Map of conversation IDs to their currently streaming title */
  streamingTitles: Record<string, string>;
}

/**
 * Conversation actions for store manipulation
 */
export interface ConversationActions {
  /** Load all conversations from database */
  loadConversations: () => Promise<void>;
  /** Create a new conversation */
  createConversation: (title?: string) => Promise<string>;
  /** Select a conversation as active */
  selectConversation: (id: string) => void;
  /** Delete a conversation */
  deleteConversation: (id: string) => Promise<void>;
  /** Update a conversation */
  updateConversation: (id: string, updates: Partial<Conversation>) => void;
  /** Clear active conversation */
  clearActiveConversation: () => void;
  /** Set error state */
  setError: (error: Error | null) => void;
  /** Generate a conversation title using streaming */
  generateTitle: (conversationId: string, messages: { role: string; content: string }[]) => Promise<void>;
}

/**
 * Combined Conversation Store type
 */
export type ConversationStore = ConversationState & ConversationActions;

/**
 * Message loading state for conversation
 */
export interface MessageLoadState {
  messages: Message[];
  isLoading: boolean;
  error: Error | null;
}
