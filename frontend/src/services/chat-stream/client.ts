/**
 * Chat Stream API Client
 * Handles streaming chat requests and response parsing
 *
 * Features:
 * - Streaming response handling with SSE parsing
 * - Abort support for cancelling requests
 * - Comprehensive error handling with custom error types
 * - Resource cleanup on completion or cancellation
 */

import { API_CONFIG } from '@/config/api';
import { ChatStreamError, StreamParseError, isAbortError } from '@/utils/error';
import { ThinkTagParser } from './parser';
import { useConversationStore } from '@/store/conversation';
import { useChatStore } from '@/store/chat/store';
import type { ChatMessage, ChatStreamOptions, StreamCallbacks } from './types';
import type { SearchMode } from '@/store/chat/types';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';
import { generateUUID } from '@/utils/id';
import { logSearchDiagnostic } from '@/services/searchDiagnostics';

const STREAM_IMAGE_SLOT_ID_PATTERN = /^[A-Za-z0-9_-]{1,40}$/;
const LANGUAGE_STORAGE_KEY = 'areqa:interface-language';
const SUPPORTED_INTERFACE_LANGUAGES = new Set(['zh-TW', 'zh-CN', 'en']);

function readInterfaceLanguage(): 'zh-TW' | 'zh-CN' | 'en' {
  if (typeof window === 'undefined') return 'en';
  const storedLanguage = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  return SUPPORTED_INTERFACE_LANGUAGES.has(storedLanguage ?? '')
    ? (storedLanguage as 'zh-TW' | 'zh-CN' | 'en')
    : 'en';
}

/**
 * Creates a streaming chat request to the local AI backend
 *
 * @param messages - Array of chat messages
 * @param callbacks - Callbacks for handling stream events
 * @param abortSignal - Optional AbortSignal for cancelling the request
 * @param useRag - Whether retrieval-augmented generation is enabled.
 * @param forceThink - Whether the backend may emit thinking content.
 * @param searchMode - Explicit web-search routing mode.
 * @param conversationId - Conversation identifier used for scoped backend state.
 * @param attachments - Optional files attached to the latest user turn.
 * @param options - Optional answer-surface controls such as live voice mode.
 *
 * @example
 * ```typescript
 * const abortController = new AbortController();
 *
 * await createChatStream(
 *   messages,
 *   {
 *     onThinkingStart: () => console.log('Thinking started'),
 *     onThinkingContent: (content) => console.log('Thinking:', content),
 *     onThinkingEnd: () => console.log('Thinking ended'),
 *     onContent: (content) => console.log('Content:', content),
 *     onCitations: (citations) => console.log('Citations:', citations),
 *     onDone: () => console.log('Done'),
 *     onError: (error) => console.error('Error:', error),
 *   },
 *   abortController.signal
 * );
 *
 * // To cancel:
 * abortController.abort();
 * ```
 */
export async function createChatStream(
  messages: ChatMessage[],
  callbacks: StreamCallbacks,
  abortSignal?: AbortSignal,
  useRag: boolean = false,
  forceThink: boolean = false,
  searchMode: SearchMode = 'never',
  conversationId: string = "",
  attachments: File[] = [],
  options: ChatStreamOptions = {},
): Promise<void> {
  const parser = new ThinkTagParser();
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

  /**
   * Cleanup function to release resources
   * Called on completion, error, or abort
   */
  const cleanup = async (): Promise<void> => {
    if (reader) {
      try {
        await reader.cancel();
      } catch {
        // Ignore errors during cleanup
      }
      reader = null;
    }
    parser.reset();
  };

  /**
   * Handle abort signal
   * Attached early to ensure cleanup happens even if aborted before stream starts
   */
  const handleAbort = (): void => {
    cleanup();
  };

  if (abortSignal) {
    // Check if already aborted
    if (abortSignal.aborted) {
      return; // Exit early if already aborted
    }
    abortSignal.addEventListener('abort', handleAbort);
  }

  try {
    const requestId = generateUUID();
    const requestPayload = {
      messages,
      conversation_id: conversationId,
      isolated_context: Boolean(useConversationStore.getState().conversations.find(
        (conversation) => conversation.id === conversationId && conversation.branchOrigin,
      )),
      use_rag: useRag,
      force_think: forceThink,
      use_web_search: searchMode === 'always',
      search_mode: searchMode,
      interface_language: readInterfaceLanguage(),
      tutor_profile: options.tutorProfile ?? 'general',
      response_mode: options.responseMode ?? 'text',
      speaking_practice: options.speakingPractice ?? false,
    };
    const uiState = useChatStore.getState();
    logSearchDiagnostic('stream_request', {
      component: 'chatStream', conversationId, requestId,
      searchMode, useWebSearch: requestPayload.use_web_search, useRag,
      uiSearchMode: uiState.searchMode, uiUseWebSearch: uiState.useWebSearch,
      attachmentCount: attachments.length,
    });
    logger.info('chat.stream_request_started', {
      conversationId, requestId, searchMode, useWebSearch: requestPayload.use_web_search, useRag,
      responseMode: requestPayload.response_mode,
      tutorProfile: requestPayload.tutor_profile,
      messageCount: messages.length,
      hasAttachments: attachments.length > 0,
    });

    const body = attachments.length > 0
      ? (() => {
          const formData = new FormData();
          formData.append('messages', JSON.stringify(requestPayload));
          for (const attachment of attachments) formData.append('attachments', attachment);
          return formData;
        })()
      : JSON.stringify(requestPayload);

    // Make the request with optional abort signal and timeout
    const fetchOptions: RequestInit = {
      method: 'POST',
      headers: { 'X-Request-ID': requestId, ...(attachments.length === 0 ? { 'Content-Type': 'application/json' } : {}) },
      body,
    };

    // Add abort signal if provided
    if (abortSignal) {
      fetchOptions.signal = abortSignal;
    }

    const response = await authenticatedFetch(API_CONFIG.chatEndpoint, fetchOptions);

    // Handle HTTP errors
    if (!response.ok) {
      let errorBody: unknown;
      let errorMessage: string;

      try {
        errorBody = await response.json();
        errorMessage =
          (errorBody as { error?: { message?: string } })?.error?.message ||
          `API Error: ${response.status}`;
      } catch {
        errorMessage = `API Error: ${response.status} ${response.statusText}`;
      }

      throw new ChatStreamError(errorMessage, response.status, errorBody);
    }

    // Get the response reader
    const bodyReader = response.body?.getReader();
    if (!bodyReader) {
      throw new Error('No response body available');
    }
    reader = bodyReader;

    const decoder = new TextDecoder();
    let pendingCitations: string[] = [];
    let suggestionsFromDone: string[] = [];

    // =================================================================
    // STREAM PROCESSING LOOP
    // Why: Read the incoming byte stream and reconstruct the SSE 
    // data blocks. Handles incomplete blocks and dispatches events.
    // =================================================================
    let buffer = '';
    while (true) {
      if (abortSignal?.aborted) {
        throw new Error('Request aborted by user');
      }

      const { done, value } = await reader.read();
      if (done) break;

      // Why: Decode binary chunks to UTF-8 text and maintain a buffer 
      // for incomplete lines split by packet boundaries.
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      
      // Keep the last partial block in the buffer
      buffer = events.pop() ?? '';

      for (const eventBlock of events) {
        if (!eventBlock.trim()) continue;

        const lines = eventBlock.split('\n');
        
        // Parse "event:" line if present (defaults to 'message')
        // Why: The backend uses custom event types like 'status' and 
        // 'sources' to provide RAG metadata alongside the message text.
        const eventTypeLine = lines.find((l) => l.startsWith('event: '));
        const eventType = eventTypeLine ? eventTypeLine.slice(7).trim() : 'message';

        const dataLine = lines.find((l) => l.startsWith('data: '));
        if (!dataLine) continue;

        const data = dataLine.slice(6).trim();

        // IF: End-of-stream signal received
        // Why: Explicitly close the stream according to protocol.
        if (data === '[DONE]') {
          if (pendingCitations.length > 0) {
            callbacks.onCitations(pendingCitations);
          }
          callbacks.onDone(suggestionsFromDone);
          return;
        }

        try {
          const chunk = JSON.parse(data);

          // IF: Event is a pipeline status update
          // Why: Update the RAGStatusPanel with the current backend progress.
          if (eventType === 'status') {
            callbacks.onStatus?.(chunk.status, chunk.message);
            continue;
          }

          // Public action telemetry contains only safe display summaries. It
          // intentionally excludes model reasoning and raw tool arguments.
          if (eventType === 'action' || eventType === 'tool_started' || eventType === 'tool_completed') {
            callbacks.onStatus?.('routing', chunk.display_message || chunk.message || '正在處理請求');
            continue;
          }

          if (eventType === 'warning') {
            callbacks.onStatus?.('routing', chunk.display_message || chunk.message || '部分功能暫時無法使用');
            continue;
          }

          // IF: Event contains structured search sources
          // Why: Display the verified literature sources used for retrieval.
          if (eventType === 'sources') {
            logSearchDiagnostic('sources_received', {
              component: 'chatStream', conversationId, requestId,
              sourceCount: Array.isArray(chunk) ? chunk.length : 0,
            });
            callbacks.onSources?.(chunk); // chunk is an array of source objects
            continue;
          }

          if (eventType === 'tool_state') {
            // Lifecycle identity stays in the image block; heartbeat/progress is not model text.
            continue;
          }

          if (eventType === 'answer_blocks') {
            callbacks.onAnswerBlocks?.(chunk); // chunk is an array of structured display blocks
            continue;
          }

          if (eventType === 'image_slot') {
            const slotId = typeof chunk.slotId === 'string' ? chunk.slotId.trim() : '';
            const contentOffset = Number.isSafeInteger(chunk.contentOffset) ? chunk.contentOffset : -1;
            const anchorAfterParagraph = Number.isSafeInteger(chunk.anchorAfterParagraph)
              ? chunk.anchorAfterParagraph
              : -1;
            if (
              STREAM_IMAGE_SLOT_ID_PATTERN.test(slotId) &&
              contentOffset >= 0 &&
              anchorAfterParagraph >= 0
            ) {
              callbacks.onImageSlot?.({ slotId, contentOffset, anchorAfterParagraph });
            }
            continue;
          }

          if (eventType === 'citations') {
            callbacks.onCitations?.(chunk); // chunk is an array of URL strings
            continue;
          }

          if (eventType === 'suggestions') {
            const suggestions = Array.isArray(chunk) ? chunk.filter((item): item is string => typeof item === 'string') : [];
            logger.info('chat.suggestions_received', { count: suggestions.length });
            callbacks.onSuggestions?.(suggestions);
            continue;
          }

          if (eventType === 'done') {
            if (chunk.suggestions) {
              suggestionsFromDone = Array.isArray(chunk.suggestions)
                ? chunk.suggestions.filter((item: unknown): item is string => typeof item === 'string')
                : [];
            }
            logger.info('chat.suggestions_done', { count: suggestionsFromDone.length });
            continue;
          }

          if (eventType === 'metadata') {
            // Check if usage payload is provided
            if (chunk.promptTokens !== undefined || chunk.totalTokens !== undefined) {
              // Get store state and set token usage!
              useChatStore.getState().setTokenUsage({
                promptTokens: chunk.promptTokens,
                completionTokens: chunk.completionTokens,
                totalTokens: chunk.totalTokens
              });
            }
            continue;
          }

          const content = chunk.choices?.[0]?.delta?.content || '';

          if (chunk.citations && chunk.citations.length > 0) {
            pendingCitations = chunk.citations;
          }

          if (content) {
            const parsedChunks = parser.parse(content);
            for (const parsed of parsedChunks) {
              switch (parsed.type) {
                case 'thinking_start':
                  callbacks.onThinkingStart();
                  break;
                case 'thinking_content':
                  if (parsed.content) callbacks.onThinkingContent(parsed.content);
                  break;
                case 'thinking_end':
                  callbacks.onThinkingEnd();
                  break;
                case 'content':
                  if (parsed.content) callbacks.onContent(parsed.content);
                  break;
              }
            }
          }
        } catch (parseError) {
          console.warn('[ChatStream] Failed to parse SSE chunk:', data, parseError);
        }
      }
    }

    // Stream ended without [DONE] signal (handle gracefully)
    if (pendingCitations.length > 0) {
      callbacks.onCitations(pendingCitations);
    }
    callbacks.onDone();
  } catch (error) {
    // Don't call error callback for user-initiated aborts
    if (isAbortError(error)) {
      console.log('[ChatStream] Request aborted by user');
      return;
    }

    // Convert to appropriate error type and call error callback
    let normalizedError: Error;

    if (error instanceof ChatStreamError) {
      normalizedError = error;
    } else if (error instanceof Error) {
      // Check if it's a fetch abort error
      if (error.name === 'AbortError') {
        console.log('[ChatStream] Request aborted');
        return;
      }
      normalizedError = error;
    } else {
      normalizedError = new Error(String(error));
    }

    callbacks.onError(normalizedError);
  } finally {
    // Clean up resources
    await cleanup();

    // Remove abort listener
    if (abortSignal) {
      abortSignal.removeEventListener('abort', handleAbort);
    }
  }
}

/**
 * Export parser class for direct usage if needed
 */
export { ThinkTagParser };

/**
 * Export error types for consumers
 */
export { ChatStreamError, StreamParseError };
