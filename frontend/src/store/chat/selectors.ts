/**
 * Chat Store Selectors
 * Pure functions for deriving data from chat state
 */

import type { ChatState, ThinkingState, DisplayMessage } from './types';

/**
 * Chat selectors for accessing derived state
 */
export const chatSelectors = {
  /**
   * Get all messages for display
   * @returns Array of display messages
   */
  displayMessages: (state: ChatState): DisplayMessage[] => state.messages,

  /**
   * Get the current thinking state
   * Includes calculated duration for real-time display
   * @returns ThinkingState object
   */
  currentThinking: (state: ChatState): ThinkingState => ({
    content: state.thinkingContent,
    isThinking: state.isThinking,
    startTime: state.thinkingStartTime,
    duration: state.thinkingStartTime
      ? Date.now() - state.thinkingStartTime
      : undefined,
  }),

  /**
   * Check if currently loading/streaming
   * @returns boolean
   */
  isLoading: (state: ChatState): boolean => state.isStreaming,

  /**
   * Get current citations
   * @returns Array of citation URLs
   */
  citations: (state: ChatState): string[] => state.currentCitations,

  /**
   * Get current error
   * @returns Error or null
   */
  error: (state: ChatState): Error | null => state.error,

  /**
   * Get the message currently being streamed
   * @returns DisplayMessage or undefined
   */
  streamingMessage: (state: ChatState): DisplayMessage | undefined => {
    if (!state.currentStreamingId) return undefined;
    return state.messages.find((msg) => msg.id === state.currentStreamingId);
  },

  /**
   * Get the last message in the conversation
   * @returns DisplayMessage or undefined
   */
  lastMessage: (state: ChatState): DisplayMessage | undefined => {
    return state.messages[state.messages.length - 1];
  },

  /**
   * Get message count
   * @returns number
   */
  messageCount: (state: ChatState): number => state.messages.length,

  /**
   * Check if conversation is empty
   * @returns boolean
   */
  isEmpty: (state: ChatState): boolean => state.messages.length === 0,

  /**
   * Get accumulated answer content being streamed
   * @returns string
   */
  currentContent: (state: ChatState): string => state.currentContent,
};

/**
 * Hook-friendly selector creators
 * Use these with useChatStore(selector) for optimized re-renders
 */
export const selectDisplayMessages = (state: ChatState) => state.messages;
export const selectIsStreaming = (state: ChatState) => state.isStreaming;
export const selectIsThinking = (state: ChatState) => state.isThinking;
export const selectThinkingContent = (state: ChatState) => state.thinkingContent;
export const selectCurrentContent = (state: ChatState) => state.currentContent;
export const selectCitations = (state: ChatState) => state.currentCitations;
export const selectError = (state: ChatState) => state.error;
