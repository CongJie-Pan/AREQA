/**
 * Chat Service
 * Integrates streaming processing with state updates and database persistence
 *
 * Features:
 * - Input validation
 * - Abort support for cancelling ongoing requests
 * - Comprehensive error handling
 * - Database persistence after streaming completes
 */

import { API_CONFIG } from '@/config/api';
import { useChatStore } from '@/store/chat';
import type { DisplayMessage, SearchMode, StreamingImageSlot } from '@/store/chat';
import type { CitationSource } from '@/components/Citations';
import { useConversationStore } from '@/store/conversation';
import { useFeatureStore } from '@/store/features';
import { useNotesStore } from '@/store/notes';
import { createChatStream } from '@/services/chat-stream';
import { databaseService } from '@/services/database';
import { syncService } from '@/services/syncService';
import { ValidationError, normalizeError } from '@/utils/error';
import { sanitizeMessagesForAPI } from '@/utils/sanitizer';
import type { ChatMessage } from '@/services/chat-stream/types';
import type { AnswerBlock, AttachmentMetadata, Message } from '@/database/schema';
import { getCurrentUserId } from '@/database/db';
import { generateUUID } from '@/utils/id';
import { filesToAttachmentMetadata } from '@/utils/attachments';
import { answerBlocksForEditedContent, persistentAnswerBlocks } from '@/utils/answerBlocks';
import { logger } from '@/utils/logger';
import { authenticatedFetch } from '@/services/authenticatedFetch';

/**
 * Active abort controller for the current stream
 * Allows cancellation of ongoing requests
 */
let currentAbortController: AbortController | null = null;
const CONVERSATION_PREVIEW_MAX_LENGTH = 100;
const ASSISTANT_EDIT_MAX_CONTENT_LENGTH = 750_000;
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
let historyLoadGeneration = 0;

export type SendMessageResponseMode = 'text' | 'voice';

export interface SendMessageOptions {
  /** Selects the backend answer surface without changing chat persistence. */
  responseMode?: SendMessageResponseMode;
  /** Called with speech-safe AREQA text chunks before the visible voice subtitle is revealed. */
  onVoiceContentChunk?: (chunk: string) => void;
  /** Optional per-turn RAG override for delegated surfaces such as Live Tutor. */
  useRag?: boolean;
  /** Optional per-turn search routing override without mutating the chat store. */
  searchMode?: SearchMode;
  /** Optional per-turn thinking override; voice responses still suppress hidden thinking. */
  forceThink?: boolean;
}

export interface SendMessageResult {
  completed: boolean;
  conversationId?: string;
  assistantMessageId?: string;
  answerContent?: string;
  finalizeVoiceResponse?: (displayContent?: string) => Promise<void>;
}

function canPersistHistory(): boolean {
  return getCurrentUserId() !== null;
}

/**
 * Patch the active conversation row after a completed assistant response.
 *
 * Args:
 *   conversationId: Persisted conversation that received the response.
 *   content: Assistant answer used only for the safe local preview.
 *   messageCountDelta: Number of messages added during this operation.
 *
 * Side Effects:
 *   Updates the in-memory conversation list without reloading the full sidebar.
 *
 * Compatibility:
 *   Title generation still owns final title persistence and its eventual list
 *   refresh. This patch only removes the extra completion-time reload that can
 *   visually churn the sidebar while image blocks are settling.
 */
function updateConversationPreviewInStore(
  conversationId: string,
  content: string,
  messageCountDelta = 0
): void {
  const store = useConversationStore.getState();
  const current = store.conversations.find((conversation) => conversation.id === conversationId);
  store.updateConversation(conversationId, {
    lastMessagePreview: content.slice(0, CONVERSATION_PREVIEW_MAX_LENGTH),
    updatedAt: new Date(),
    ...(current
      ? { messageCount: Math.max(0, current.messageCount + messageCountDelta) }
      : {}),
  });
}

function patchConversationAfterTurnDeletion(conversationId: string, remainingMessages: DisplayMessage[]): void {
  const conversationMessages = remainingMessages.filter((message) => message.conversationId === conversationId);
  const latestMessage = conversationMessages.at(-1);

  useConversationStore.getState().updateConversation(conversationId, {
    lastMessagePreview: latestMessage?.content.slice(0, CONVERSATION_PREVIEW_MAX_LENGTH) ?? '',
    updatedAt: new Date(),
    messageCount: conversationMessages.length,
  });
}

function patchConversationPreviewIfLatest(message: DisplayMessage, content: string): void {
  const conversationMessages = useChatStore
    .getState()
    .messages
    .filter((item) => item.conversationId === message.conversationId);
  const latestMessage = conversationMessages.at(-1);

  if (latestMessage?.id !== message.id) return;

  updateConversationPreviewInStore(message.conversationId, content);
}

function conversationHistoryDebugLogsEnabled(): boolean {
  return useFeatureStore.getState().conversationHistoryDebugLogs;
}

type ConversationHistoryDebugContext = {
  activeConversationId?: string | null;
  assistantMessageCount?: number;
  clearBeforeLoad?: boolean;
  component: string;
  conversationId: string;
  deletionMarkerCount?: number;
  displayMessageCount?: number;
  durationMs?: number;
  error?: unknown;
  latestMessageUpdatedAt?: string | null;
  latestQueuedAt?: string | null;
  messageCount?: number;
  pendingSyncCount?: number;
  previousActiveConversationId?: string | null;
  status?: number | string;
  userMessageCount?: number;
};

function safeConversationHistoryDebugContext(
  context: ConversationHistoryDebugContext,
): Record<string, string | number | boolean | null> {
  const safe: Record<string, string | number | boolean | null> = {};

  Object.entries(context).forEach(([key, value]) => {
    if (key === 'error') {
      safe.errorName = value instanceof Error ? value.name : typeof value;
      return;
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || value === null) {
      safe[key] = value;
    }
  });

  return safe;
}

export function logConversationHistoryDebugEvent(
  eventName: string,
  context: ConversationHistoryDebugContext,
): void {
  if (!conversationHistoryDebugLogsEnabled()) return;

  const safeContext = safeConversationHistoryDebugContext(context);
  void authenticatedFetch(`${BACKEND_URL}/api/v1/conversation-history/debug-log`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      event: eventName,
      context: safeContext,
    }),
  })
    .then((response) => {
      if (!response.ok) {
        logger.warn('chat_history_backend_debug_forward_failed', {
          component: context.component,
          conversationId: context.conversationId,
          eventName,
          status: response.status,
        });
      }
    })
    .catch((error) => {
      logger.warn('chat_history_backend_debug_forward_failed', {
        component: context.component,
        conversationId: context.conversationId,
        eventName,
        reason: error instanceof Error ? error.message : String(error),
      });
    });
}

function logConversationHistoryDiagnostics(
  eventName: string,
  context: {
    conversationId: string;
    userId: string;
    durationMs?: number;
    displayMessageCount?: number;
    error?: unknown;
  },
): void {
  if (!conversationHistoryDebugLogsEnabled()) return;

  void databaseService.message.getConversationDiagnostics(context.conversationId, context.userId)
    .then((diagnostics) => {
      const payload = {
        component: 'chatService',
        conversationId: context.conversationId,
        durationMs: context.durationMs,
        displayMessageCount: context.displayMessageCount,
        messageCount: diagnostics.messageCount,
        userMessageCount: diagnostics.userMessageCount,
        assistantMessageCount: diagnostics.assistantMessageCount,
        pendingSyncCount: diagnostics.pendingSyncCount,
        deletionMarkerCount: diagnostics.deletionMarkerCount,
        latestMessageUpdatedAt: diagnostics.latestMessageUpdatedAt?.toISOString() ?? null,
        latestQueuedAt: diagnostics.latestQueuedAt?.toISOString() ?? null,
      };
      if (context.error) {
        logger.error(
          eventName,
          context.error instanceof Error ? context.error : new Error(String(context.error)),
          payload,
        );
        logConversationHistoryDebugEvent(eventName, { ...payload, error: context.error });
        return;
      }
      logger.info(eventName, payload);
      logConversationHistoryDebugEvent(eventName, payload);
    })
    .catch((diagnosticsError) => {
      logger.warn('chat_history_load_diagnostics_failed', {
        component: 'chatService',
        conversationId: context.conversationId,
        eventName,
        reason: diagnosticsError instanceof Error ? diagnosticsError.message : String(diagnosticsError),
      });
    });
}

/**
 * Prepare messages for API by filtering out invalid messages
 * Filters out:
 * - Messages with the specified exclude ID (usually placeholder)
 * - Empty assistant messages (can occur when stream is stopped during thinking)
 *
 * @param messages - Raw messages from store
 * @param excludeMessageId - Optional message ID to exclude
 * @returns Filtered messages ready for API
 */
function formatAttachmentContext(attachments: AttachmentMetadata[] | undefined): string {
  if (!attachments || attachments.length === 0) return '';
  const lines = attachments.slice(0, 5).map((attachment, index) => {
    const sizeKb = Math.max(1, Math.ceil(attachment.sizeBytes / 1024));
    return `${index + 1}. ${attachment.name} (${attachment.mediaType}, ${sizeKb} KB)`;
  });
  return [
    '',
    '[Original attachments retained for context; binary file bytes are not resent on edit]',
    ...lines,
  ].join('\n');
}

function messageContentForAPI(message: DisplayMessage): string {
  return `${message.content}${formatAttachmentContext(message.attachments)}`;
}

function prepareMessagesForAPI(
  messages: DisplayMessage[],
  excludeMessageId?: string,
  conversationId?: string
): ChatMessage[] {
  const mappedMessages = messages
    .filter((msg) => !excludeMessageId || msg.id !== excludeMessageId)
    .filter((msg) => !conversationId || msg.conversationId === conversationId)
    .filter((msg) => !(msg.role === 'assistant' && msg.content.trim() === ''))
    .map((msg) => ({
      role: msg.role === 'user' ? 'user' : 'assistant',
      content: messageContentForAPI(msg),
    })) as ChatMessage[];
    
  return sanitizeMessagesForAPI(mappedMessages) as ChatMessage[];
}

/**
 * Validate message content before sending
 * @param content - Message content to validate
 * @throws ValidationError if content is invalid
 */
function validateMessageContent(
  content: string,
  hasAttachments = false,
  maxLength = API_CONFIG.maxMessageLength
): void {
  if (!content && !hasAttachments) {
    throw new ValidationError('Message content is required', 'content');
  }

  const trimmedContent = content.trim();

  if (!hasAttachments && trimmedContent.length < API_CONFIG.minMessageLength) {
    throw new ValidationError('Message cannot be empty', 'content');
  }

  if (trimmedContent.length > maxLength) {
    throw new ValidationError(
      `Message is too long (max ${maxLength} characters)`,
      'content'
    );
  }
}

/**
 * Send a message and handle streaming response
 *
 * @param content - User message content
 * @param conversationId - Optional conversation ID (creates new if not provided)
 * @param attachments - Optional files to attach to the user turn.
 * @param options - Optional answer-surface controls. Live voice uses this to
 *   request speech-safe prose while deferring visible text to spoken transcript
 *   deltas.
 * @returns Promise that resolves when streaming is complete. Voice callers also
 *   receive the authoritative answer and a finalizer that persists it after
 *   speech playback ends.
 *
 * @throws ValidationError if content is invalid
 * @throws Error if streaming fails
 *
 * @example
 * ```typescript
 * try {
 *   await sendMessage('What is the weather like?');
 * } catch (error) {
 *   const normalizedError = normalizeError(error);
 *   if (error instanceof ValidationError) {
 *     console.log('Invalid input:', error.message);
 *   } else {
 *     console.error('Stream error:', normalizedError);
 *   }
 * }
 * ```
 */
export async function sendMessage(
  content: string,
  conversationId?: string,
  attachments: File[] = [],
  options: SendMessageOptions = {},
): Promise<SendMessageResult> {
  // Validate input
  validateMessageContent(content, attachments.length > 0);
  const sanitizedContent = content.trim() || (attachments.length > 0 ? '請分析我附加的檔案。' : '');
  const attachmentMetadata = filesToAttachmentMetadata(attachments);
  const responseMode = options.responseMode ?? 'text';
  const isVoiceResponse = responseMode === 'voice';

  // Cancel any ongoing stream
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }

  // Create new abort controller for this request
  currentAbortController = new AbortController();
  const abortSignal = currentAbortController.signal;

  const chatStore = useChatStore.getState();
  const conversationStore = useConversationStore.getState();
  const shouldPersist = canPersistHistory();

  // Create or use existing conversation
  let activeConversationId = shouldPersist
    ? conversationId ?? conversationStore.activeConversationId
    : undefined;
  let isNewConversation = false;

  if (!activeConversationId) {
    isNewConversation = true;
    if (shouldPersist) {
      // Create new conversation in database first to get the ID
      const conversation = await databaseService.conversation.create();
      activeConversationId = conversation.id;

      // Add to the conversation list in store without selecting yet
      // This avoids triggering the useEffect in ChatContainer prematurely
      useConversationStore.setState((state) => ({
        conversations: [conversation, ...state.conversations],
      }));
    } else {
      activeConversationId = generateUUID();
    }
  }

  // Add user message to store
  const userMessageId = chatStore.addUserMessage(sanitizedContent, activeConversationId, attachmentMetadata);

  // Save user message to database
  if (shouldPersist) {
    await databaseService.message.add(activeConversationId, {
      id: userMessageId,
      role: 'user',
      content: sanitizedContent,
      ...(attachmentMetadata.length > 0 ? { attachments: attachmentMetadata } : {}),
    });
  }

  // If this was a new conversation, now set it as active
  // This will trigger the useEffect in ChatContainer, but we've already
  // added the message to both store and database.
  if (isNewConversation) {
    conversationStore.selectConversation(activeConversationId);
  }

  // Add assistant message placeholder
  const assistantMessageId = chatStore.addAssistantMessage(activeConversationId);

  // Start streaming
  chatStore.startStreaming(assistantMessageId);

  // Build messages array for API using shared filter function
  // We use the messages FROM THE STORE to ensure consistency
  const latestState = useChatStore.getState();
  let messages = prepareMessagesForAPI(
    latestState.messages,
    assistantMessageId,
    activeConversationId
  );

  // Fallback: If for some reason the store state isn't reflected yet (async lag),
  // manually add the current user message to ensure the API doesn't fail.
  if (messages.length === 0 && sanitizedContent) {
    messages = [{
      role: 'user',
      content: sanitizedContent
    }];
  }

  if (attachments.length > 0) {
    const latestUserMessage = [...messages].reverse().find((item) => item.role === 'user');
    if (latestUserMessage) latestUserMessage.content = sanitizedContent;
  }

  // Safety check: Don't send empty messages to API
  if (messages.length === 0) {
    chatStore.resetStreamingState();
    chatStore.setError(new Error('無法準備對話內容，請重新嘗試。'));
    return { completed: false };
  }

  // Track state for database save
  let thinkingContent = '';
  let thinkingStartTime: number | null = null;
  let answerContent = '';
  let citations: string[] = [];
  let sourcesPayload: CitationSource[] = [];
  let answerBlocksPayload: AnswerBlock[] = [];
  let suggestionsList: string[] = [];
  let completed = false;
  let hasFinalizedAssistant = false;
  const effectiveUseRag = options.useRag ?? chatStore.useRag;
  const effectiveSearchMode = options.searchMode ?? chatStore.searchMode;
  const effectiveForceThink = isVoiceResponse ? false : (options.forceThink ?? chatStore.forceThink);
  const effectiveTutorProfile = chatStore.tutorProfile;

  // Capture conversation ID for async callback (prevents closure issues)
  const conversationIdForSave = activeConversationId;

  /**
   * Finalize and persist the assistant message exactly once.
   *
   * Args:
   *   displayContent: Optional visible subtitle transcript. Persistence still
   *     uses AREQA's authoritative answer text so speech transcript drift does
   *     not corrupt history.
   *
   * Side Effects:
   *   Ends the active chat stream, writes the assistant message to storage when
   *   history persistence is available, and refreshes the conversation preview.
   */
  const finalizeAssistantMessage = async (displayContent?: string): Promise<void> => {
    if (hasFinalizedAssistant) return;
    hasFinalizedAssistant = true;
    if (displayContent !== undefined) {
      chatStore.updateMessageContent(assistantMessageId, displayContent);
      useChatStore.setState({ currentContent: displayContent });
    }
    chatStore.endStreaming(
      sourcesPayload.length > 0 ? sourcesPayload : undefined,
      answerBlocksPayload.length > 0 ? answerBlocksPayload : undefined,
    );

    if (suggestionsList.length > 0) {
      chatStore.updateAssistantMessage(assistantMessageId, { suggestions: suggestionsList });
    }

    const thinkingDuration = thinkingStartTime ? Date.now() - thinkingStartTime : undefined;
    const messageData: Omit<Message, 'id' | 'conversationId' | 'createdAt' | 'userId'> = {
      role: 'assistant',
      content: answerContent,
    };
    if (thinkingContent) messageData.reasoning = { content: thinkingContent, duration: thinkingDuration };
    if (citations.length > 0) messageData.citations = citations;
    if (sourcesPayload.length > 0) messageData.sources = sourcesPayload;
    const answerBlocksForPersistence = persistentAnswerBlocks(answerBlocksPayload);
    if (answerBlocksForPersistence) messageData.answerBlocks = answerBlocksForPersistence;
    if (suggestionsList.length > 0) messageData.suggestions = suggestionsList;
    if (shouldPersist) {
      await databaseService.message.add(conversationIdForSave, {
        id: assistantMessageId,
        ...messageData,
      });
    }
    if (shouldPersist) updateConversationPreviewInStore(conversationIdForSave, answerContent, 2);
    if (shouldPersist && messages.length === 1 && answerContent) {
      useConversationStore.getState().generateTitle(conversationIdForSave, [
        ...messages, { role: 'assistant', content: answerContent },
      ]);
    }
    currentAbortController = null;
  };

  try {
    const callbacks = {
      onThinkingStart: () => {
        // Hide the RAG panel at the first generation boundary. The first
        // thinking/content token may arrive after this callback, and backend
        // streams are not guaranteed to emit a separate `generating` status.
        chatStore.setRagStatus('generating');
        if (!effectiveForceThink) return;
        thinkingStartTime = Date.now();
        // Store handles isThinking state
      },

      onThinkingContent: (chunk: string) => {
        if (!effectiveForceThink) return;
        thinkingContent += chunk;
        chatStore.appendThinkingContent(chunk);
      },

      onThinkingEnd: () => {
        if (!effectiveForceThink) return;
        chatStore.endThinking();
      },

      onContent: (chunk: string) => {
        answerContent += chunk;
        if (isVoiceResponse) {
          options.onVoiceContentChunk?.(chunk);
          return;
        }
        chatStore.appendContent(chunk);
      },

      onCitations: (citationUrls: string[]) => {
        citations = citationUrls;
        chatStore.setCitations(citationUrls);
      },

      onStatus: (status: 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done', message: string) => {
        chatStore.setRagStatus(status, message);
      },

      onSources: (sources: CitationSource[]) => {
        sourcesPayload = sources;
        chatStore.setRagStatus('sources_ready');
        chatStore.setRagSources(sources);
      },

      onAnswerBlocks: (blocks: AnswerBlock[]) => {
        answerBlocksPayload = blocks;
        chatStore.setAnswerBlocks(blocks);
      },

      onImageSlot: (slot: StreamingImageSlot) => {
        chatStore.addImageSlot(slot);
      },

      onSuggestions: (suggestions: string[]) => {
        suggestionsList = suggestions;
        chatStore.updateAssistantMessage(assistantMessageId, { suggestions });
      },

      onDone: async (suggestions?: string[]) => {
        completed = true;
        if (suggestions && suggestions.length > 0) {
          suggestionsList = suggestions;
          chatStore.updateAssistantMessage(assistantMessageId, { suggestions });
        }
        if (!isVoiceResponse) {
          // Pass closure-captured metadata directly to avoid races where SSE
          // events have not committed to Zustand before the terminal event.
          await finalizeAssistantMessage();
        }
      },

      onError: (error: Error) => {
        chatStore.setError(error);
        chatStore.endStreaming();
        currentAbortController = null;
      },
    };

    if (attachments.length > 0) {
      await createChatStream(
        messages,
        callbacks,
        abortSignal,
        effectiveUseRag,
        effectiveForceThink,
        effectiveSearchMode,
        activeConversationId,
        attachments,
        { responseMode, tutorProfile: effectiveTutorProfile },
      );
    } else {
      await createChatStream(
        messages,
        callbacks,
        abortSignal,
        effectiveUseRag,
        effectiveForceThink,
        effectiveSearchMode,
        activeConversationId,
        [],
        { responseMode, tutorProfile: effectiveTutorProfile },
      );
    }

    if (!isVoiceResponse) return { completed };
    return {
      completed,
      conversationId: conversationIdForSave,
      assistantMessageId,
      answerContent,
      finalizeVoiceResponse: finalizeAssistantMessage,
    };
  } catch (error) {
    // Clear abort controller
    currentAbortController = null;

    const err = normalizeError(error);
    chatStore.setError(err);
    chatStore.endStreaming();
    throw err;
  }
}

/**
 * Directly insert a completed assistant message into the chat history.
 * Useful for proactive AI messages that should be visible in the chat.
 * 
 * @param content - The message content
 * @param conversationId - Target conversation ID
 */
export async function insertAssistantMessage(
  content: string,
  conversationId?: string
): Promise<void> {
  const sanitizedContent = content.trim();
  if (!sanitizedContent) return;

  const chatStore = useChatStore.getState();
  const conversationStore = useConversationStore.getState();
  const shouldPersist = canPersistHistory();

  // Create or use existing conversation
  let activeConversationId = shouldPersist
    ? conversationId ?? conversationStore.activeConversationId
    : undefined;
  let isNewConversation = false;

  if (!activeConversationId) {
    isNewConversation = true;
    if (shouldPersist) {
      const conversation = await databaseService.conversation.create();
      activeConversationId = conversation.id;
      useConversationStore.setState((state) => ({
        conversations: [conversation, ...state.conversations],
      }));
    } else {
      activeConversationId = generateUUID();
    }
  }

  // Add assistant message to store
  const messageId = chatStore.addAssistantMessage(activeConversationId);
  chatStore.updateAssistantMessage(messageId, { content: sanitizedContent });
  chatStore.endStreaming();

  // Save to database
  if (shouldPersist) {
    await databaseService.message.add(activeConversationId, {
      id: messageId,
      role: 'assistant',
      content: sanitizedContent,
    });
  }

  if (isNewConversation) {
    conversationStore.selectConversation(activeConversationId);
  }
}

/**
 * Cancel the current streaming request
 * Safe to call even if no request is in progress
 * Preserves accumulated thinking content if stopped during thinking phase
 * Saves partial response to database to prevent data loss
 */
export async function cancelCurrentStream(): Promise<void> {
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }

  const chatStore = useChatStore.getState();
  const conversationStore = useConversationStore.getState();

  // Capture current state before any changes
  const streamingMessageId = chatStore.currentStreamingId;
  const hasThinkingContent = chatStore.isThinking && chatStore.thinkingContent;
  const thinkingContent = chatStore.thinkingContent;
  const thinkingStartTime = chatStore.thinkingStartTime;
  const currentContent = chatStore.currentContent;
  const hasAssistantContent = Boolean(currentContent || thinkingContent);

  // If we're in thinking phase, save the accumulated thinking content to the message
  if (hasThinkingContent) {
    chatStore.endThinking();
  }

  if (!hasAssistantContent && streamingMessageId) {
    chatStore.removeMessage(streamingMessageId);
  } else {
    // Finalize the streaming message with whatever content we have.
    chatStore.endStreaming();
  }

  // Save partial response to database to prevent data loss on page refresh
  const activeConversationId = conversationStore.activeConversationId;
  if (hasAssistantContent && canPersistHistory() && streamingMessageId && activeConversationId) {
    try {
      const messageData: Omit<Message, 'id' | 'conversationId' | 'createdAt' | 'userId'> = {
        role: 'assistant',
        content: currentContent || '',
      };

      // Include thinking/reasoning if we have it
      if (thinkingContent) {
        const thinkingDuration = thinkingStartTime
          ? Date.now() - thinkingStartTime
          : undefined;
        messageData.reasoning = {
          content: thinkingContent,
          duration: thinkingDuration,
        };
      }

      await databaseService.message.add(activeConversationId, {
        id: streamingMessageId,
        ...messageData,
      });
    } catch (error) {
      // Log but don't throw - cancellation should always succeed
      console.error('Failed to save partial message on cancel:', error);
    }
  }

  // Clear the streaming state (but message data is preserved in store)
  chatStore.resetStreamingState();
}

/**
 * Check if a stream is currently in progress
 * @returns True if a stream is active
 */
export function isStreamActive(): boolean {
  return currentAbortController !== null && !currentAbortController.signal.aborted;
}

/**
 * Load messages for a conversation
 * @param conversationId - Conversation ID
 * @param options - Loading behavior flags.
 */
export async function loadMessages(
  conversationId: string,
  options: { clearBeforeLoad?: boolean; isStale?: () => boolean } = {},
): Promise<void> {
  const chatStore = useChatStore.getState();
  const shouldClearBeforeLoad = options.clearBeforeLoad ?? true;
  const loadStartedAt = performance.now();

  if (shouldClearBeforeLoad) {
    chatStore.clearMessages();
    chatStore.resetStreamingState();
  }

  const userId = getCurrentUserId();
  if (!userId) {
    if (conversationHistoryDebugLogsEnabled()) {
      logger.warn('chat_history_load_skipped_auth', {
        component: 'chatService',
        conversationId,
      });
      logConversationHistoryDebugEvent('chat_history_load_skipped_auth', {
        component: 'chatService',
        conversationId,
      });
    }
    return;
  }

  try {
    if (conversationHistoryDebugLogsEnabled()) {
      logger.info('chat_history_load_started', {
        component: 'chatService',
        conversationId,
        clearBeforeLoad: shouldClearBeforeLoad,
      });
      logConversationHistoryDebugEvent('chat_history_load_started', {
        component: 'chatService',
        conversationId,
        clearBeforeLoad: shouldClearBeforeLoad,
      });
    }
    await syncService.pullConversationMessages(conversationId, userId, {
      authoritative: true,
    });
    logConversationHistoryDiagnostics('chat_history_cloud_hydration_finished', {
      conversationId,
      userId,
      durationMs: Math.round(performance.now() - loadStartedAt),
    });
    if (options.isStale?.()) {
      logger.info('chat_history_hydration_stale_ignored', {
        component: 'chatService',
        conversationId,
        durationMs: Math.round(performance.now() - loadStartedAt),
      });
      return;
    }

    const messages = await databaseService.message.getByConversationId(conversationId, userId);
    logConversationHistoryDiagnostics('chat_history_local_messages_read', {
      conversationId,
      userId,
      durationMs: Math.round(performance.now() - loadStartedAt),
    });

    if (options.isStale?.()) {
      logger.info('chat_history_load_stale_ignored', {
        component: 'chatService',
        conversationId,
        durationMs: Math.round(performance.now() - loadStartedAt),
      });
      return;
    }

    if (!shouldClearBeforeLoad) {
      chatStore.resetStreamingState();
    }
    chatStore.setMessages(messages);
    logConversationHistoryDiagnostics('chat_history_messages_committed', {
      conversationId,
      userId,
      durationMs: Math.round(performance.now() - loadStartedAt),
      displayMessageCount: messages.length,
    });
  } catch (error) {
    const err = normalizeError(error);
    logConversationHistoryDiagnostics('chat_history_load_failed', {
      conversationId,
      userId,
      durationMs: Math.round(performance.now() - loadStartedAt),
      error: err,
    });
    chatStore.setError(err);
    throw err;
  }
}

/**
 * Start a new conversation
 * Clears current messages and creates new conversation
 * @returns New conversation ID
 */
export async function startNewConversation(): Promise<string> {
  // Cancel any ongoing stream
  await cancelCurrentStream();
  historyLoadGeneration += 1;

  const chatStore = useChatStore.getState();
  const conversationStore = useConversationStore.getState();

  // Aggressively clear UI state
  chatStore.clearMessages();
  chatStore.resetStreamingState();

  if (!canPersistHistory()) {
    conversationStore.clearActiveConversation();
    return generateUUID();
  }

  // Create new conversation
  const conversationId = await conversationStore.createConversation();
  return conversationId;
}

/**
 * Switch to a different conversation
 * @param conversationId - Conversation ID to switch to
 */
export async function switchConversation(conversationId: string): Promise<void> {
  const switchStartedAt = performance.now();
  if (conversationHistoryDebugLogsEnabled()) {
    logger.info('chat_history_switch_requested', {
      component: 'chatService',
      conversationId,
      previousActiveConversationId: useConversationStore.getState().activeConversationId,
    });
    logConversationHistoryDebugEvent('chat_history_switch_requested', {
      component: 'chatService',
      conversationId,
      previousActiveConversationId: useConversationStore.getState().activeConversationId,
    });
  }
  // Cancel any ongoing stream
  await cancelCurrentStream();

  const conversationStore = useConversationStore.getState();

  if (!canPersistHistory()) {
    if (conversationHistoryDebugLogsEnabled()) {
      logger.warn('chat_history_switch_skipped_auth', {
        component: 'chatService',
        conversationId,
        durationMs: Math.round(performance.now() - switchStartedAt),
      });
      logConversationHistoryDebugEvent('chat_history_switch_skipped_auth', {
        component: 'chatService',
        conversationId,
        durationMs: Math.round(performance.now() - switchStartedAt),
      });
    }
    return;
  }
  const requestGeneration = ++historyLoadGeneration;
  const isStale = () => requestGeneration !== historyLoadGeneration;

  // Keep the currently rendered messages until the target conversation is
  // ready. Clearing first makes MessageList briefly render the new-chat empty
  // state during IndexedDB reads.
  conversationStore.setMessageHandoffLoading(true);
  try {
    await loadMessages(conversationId, { clearBeforeLoad: false, isStale });
    if (isStale()) {
      logger.info('chat_history_switch_stale_ignored', {
        component: 'chatService',
        conversationId,
      });
      return;
    }
    conversationStore.selectConversation(conversationId);
    if (conversationHistoryDebugLogsEnabled()) {
      logger.info('chat_history_switch_completed', {
        component: 'chatService',
        conversationId,
        activeConversationId: useConversationStore.getState().activeConversationId,
        displayMessageCount: useChatStore.getState().messages.length,
        durationMs: Math.round(performance.now() - switchStartedAt),
      });
      logConversationHistoryDebugEvent('chat_history_switch_completed', {
        component: 'chatService',
        conversationId,
        activeConversationId: useConversationStore.getState().activeConversationId,
        displayMessageCount: useChatStore.getState().messages.length,
        durationMs: Math.round(performance.now() - switchStartedAt),
      });
    }
  } finally {
    if (!isStale()) {
      useConversationStore.getState().setMessageHandoffLoading(false);
    }
  }
}

/**
 * Delete current conversation and switch to another
 * @param conversationId - Conversation ID to delete
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  const conversationStore = useConversationStore.getState();
  const chatStore = useChatStore.getState();
  const wasActiveConversation = conversationStore.activeConversationId === conversationId;

  // If deleting the active conversation, clear UI immediately
  if (wasActiveConversation) {
    await cancelCurrentStream();
    chatStore.clearMessages();
    chatStore.resetStreamingState();
  }

  // Delete conversation (this will update activeConversationId to null if it was active)
  await conversationStore.deleteConversation(conversationId);

  // Double check cleanup if it was the active conversation
  if (wasActiveConversation) {
    chatStore.clearMessages();
    chatStore.resetStreamingState();
  }
}

/**
 * Delete the latest completed assistant turn and the user query immediately
 * before it.
 *
 * @param assistantMessageId - The bottom assistant message selected by the user.
 * @throws Error when the target is not the latest completed assistant message
 * or does not have an immediately preceding user query in the same conversation.
 */
export async function deleteLatestConversationTurn(assistantMessageId: string): Promise<void> {
  const chatStore = useChatStore.getState();
  const conversationStore = useConversationStore.getState();
  const messages = chatStore.messages;
  const targetIndex = messages.findIndex((message) => message.id === assistantMessageId);

  if (targetIndex === -1) throw new Error('Message not found');

  const assistantMessage = messages[targetIndex];
  const conversationId = assistantMessage.conversationId ?? conversationStore.activeConversationId;
  if (!conversationId) throw new Error('No conversation found for the assistant reply');

  const conversationMessages = messages.filter((message) => message.conversationId === conversationId);
  const latestConversationMessage = conversationMessages.at(-1);
  const targetConversationIndex = conversationMessages.findIndex((message) => message.id === assistantMessage.id);

  if (
    assistantMessage.role !== 'assistant' ||
    assistantMessage.isStreaming ||
    chatStore.currentStreamingId === assistantMessage.id ||
    latestConversationMessage?.id !== assistantMessage.id
  ) {
    throw new Error('Only the latest completed assistant reply can be deleted');
  }

  let pairedUserIndex = -1;
  for (let index = targetConversationIndex - 1; index >= 0; index -= 1) {
    if (conversationMessages[index].role === 'user') {
      pairedUserIndex = index;
      break;
    }
  }
  const pairedUserMessage = pairedUserIndex >= 0 ? conversationMessages[pairedUserIndex] : undefined;
  if (!pairedUserMessage) {
    throw new Error('Latest assistant reply does not have a paired user query');
  }

  let deletionStartIndex = pairedUserIndex;
  for (let index = pairedUserIndex - 1; index >= 0; index -= 1) {
    if (conversationMessages[index].role === 'assistant') break;
    deletionStartIndex = index;
  }

  const idsToDelete = conversationMessages
    .slice(deletionStartIndex, targetConversationIndex + 1)
    .map((message) => message.id);

  for (const id of idsToDelete) {
    chatStore.removeMessage(id);
  }
  chatStore.resetStreamingState();
  patchConversationAfterTurnDeletion(conversationId, useChatStore.getState().messages);

  if (canPersistHistory()) {
    try {
      await databaseService.message.deleteManyByConversationId(conversationId, idsToDelete);
    } catch (error) {
      logger.warn('chat_latest_turn_delete_sync_failed', {
        component: 'chatService',
        conversationId,
        assistantMessageId: assistantMessage.id,
        userMessageId: pairedUserMessage.id,
        deletedCount: idsToDelete.length,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  logger.info('chat_latest_turn_deleted', {
    component: 'chatService',
    conversationId,
    assistantMessageId: assistantMessage.id,
    userMessageId: pairedUserMessage.id,
    deletedCount: idsToDelete.length,
    persisted: canPersistHistory(),
  });
}

/**
 * Initialize chat service
 * Loads conversations on app start
 */
export async function initializeChatService(userId?: string): Promise<void> {
  const conversationStore = useConversationStore.getState();
  const authenticatedUserId = userId ?? getCurrentUserId();
  if (authenticatedUserId) {
    await conversationStore.loadConversations(authenticatedUserId);
    void databaseService.message.flushPendingCloudSync(authenticatedUserId);
  }
}

/**
 * Regenerate an AI message
 * Removes the old AI message and generates a new response based on existing conversation
 * Does NOT create a new user message
 * @param messageId - The AI message ID to regenerate
 */
export async function regenerateMessage(messageId: string): Promise<void> {
  // Cancel any ongoing stream
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }

  const chatStore = useChatStore.getState();
  const conversationStore = useConversationStore.getState();
  const shouldPersist = canPersistHistory();
  const messages = chatStore.messages;

  // Find the message index
  const messageIndex = messages.findIndex((msg) => msg.id === messageId);
  if (messageIndex === -1) {
    throw new Error('Message not found');
  }

  const targetMessage = messages[messageIndex];
  if (targetMessage.role !== 'assistant') {
    throw new Error('Can only regenerate assistant messages');
  }

  const activeConversationId = conversationStore.activeConversationId ?? targetMessage.conversationId;
  if (!activeConversationId) {
    throw new Error('No active conversation');
  }

  const apiMessages = prepareMessagesForAPI(
    messages.slice(0, messageIndex),
    undefined,
    activeConversationId
  );

  // Safety check: Don't send empty messages to API
  if (apiMessages.length === 0) {
    chatStore.resetStreamingState();
    chatStore.setError(new Error('無法準備對話內容（歷史記錄為空），無法重新生成。'));
    return;
  }

  // Create new abort controller for this request
  currentAbortController = new AbortController();
  const abortSignal = currentAbortController.signal;

  const originalAssistantMessage = { ...targetMessage };
  chatStore.updateAssistantMessage(messageId, {
    content: '',
    reasoning: undefined,
    citations: undefined,
    sources: undefined,
    answerBlocks: undefined,
    suggestions: undefined,
    isStreaming: true,
  });

  // Start streaming
  chatStore.startStreaming(messageId);

  const latestState = useChatStore.getState();

  // Track state for database save
  let thinkingContent = '';
  let thinkingStartTime: number | null = null;
  let answerContent = '';
  let citations: string[] = [];
  let sourcesPayload: CitationSource[] = [];
  let answerBlocksPayload: AnswerBlock[] = [];
  let suggestionsList: string[] = [];

  try {
    await createChatStream(
      apiMessages,
      {
        onThinkingStart: () => {
          // Hide the RAG panel at the first generation boundary. The first
          // thinking/content token may arrive after this callback, and backend
          // streams are not guaranteed to emit a separate `generating` status.
          chatStore.setRagStatus('generating');
          if (!latestState.forceThink) return;
          thinkingStartTime = Date.now();
        },

        onThinkingContent: (chunk: string) => {
          if (!latestState.forceThink) return;
          thinkingContent += chunk;
          chatStore.appendThinkingContent(chunk);
        },

        onThinkingEnd: () => {
          if (!latestState.forceThink) return;
          chatStore.endThinking();
        },

        onContent: (chunk: string) => {
          answerContent += chunk;
          chatStore.appendContent(chunk);
        },

        onCitations: (citationUrls: string[]) => {
          citations = citationUrls;
          chatStore.setCitations(citationUrls);
        },

        onStatus: (status: 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done', message: string) => {
          chatStore.setRagStatus(status, message);
        },

        onSources: (sources: CitationSource[]) => {
          sourcesPayload = sources;
          chatStore.setRagStatus('sources_ready');
          chatStore.setRagSources(sources);
        },

        onAnswerBlocks: (blocks: AnswerBlock[]) => {
          answerBlocksPayload = blocks;
          chatStore.setAnswerBlocks(blocks);
        },

        onImageSlot: (slot: StreamingImageSlot) => {
          chatStore.addImageSlot(slot);
        },

        onSuggestions: (suggestions: string[]) => {
          suggestionsList = suggestions;
          chatStore.updateAssistantMessage(messageId, { suggestions });
        },

        onDone: async (suggestions?: string[]) => {
          // Pass sourcesPayload directly to avoid race condition where
          // state.ragSources may not yet be set when endStreaming reads it.
          chatStore.endStreaming(
            sourcesPayload.length > 0 ? sourcesPayload : undefined,
            answerBlocksPayload.length > 0 ? answerBlocksPayload : undefined,
          );

          // Update message with final suggestions if received in done event
          if (suggestions && suggestions.length > 0) {
            suggestionsList = suggestions;
            chatStore.updateAssistantMessage(messageId, { suggestions });
          }

          // Calculate thinking duration
          const thinkingDuration = thinkingStartTime
            ? Date.now() - thinkingStartTime
            : undefined;

          // Save assistant message to database
          const messageData: Omit<Message, 'id' | 'conversationId' | 'createdAt' | 'userId'> = {
            role: 'assistant',
            content: answerContent,
          };

          if (thinkingContent) {
            messageData.reasoning = {
              content: thinkingContent,
              duration: thinkingDuration,
            };
          }

          if (citations.length > 0) {
            messageData.citations = citations;
          }

          if (sourcesPayload.length > 0) {
            messageData.sources = sourcesPayload;
          }

          const answerBlocksForPersistence = persistentAnswerBlocks(answerBlocksPayload);
          if (answerBlocksForPersistence) messageData.answerBlocks = answerBlocksForPersistence;

          if (suggestionsList.length > 0) {
            messageData.suggestions = suggestionsList;
          }

          if (shouldPersist) {
            await databaseService.message.update(messageId, messageData);
          }


          if (shouldPersist) updateConversationPreviewInStore(activeConversationId, answerContent);

          // Trigger title generation if this is the first assistant response
          if (shouldPersist && apiMessages.length === 1 && answerContent) {
            const titleMessages = [
              ...apiMessages,
              { role: 'assistant', content: answerContent }
            ];
            // Start title generation in background (streaming to store)
            useConversationStore.getState().generateTitle(activeConversationId, titleMessages);
          }

          // Clear abort controller reference
          currentAbortController = null;
        },

        onError: (error: Error) => {
          chatStore.setError(error);
          chatStore.endStreaming();
          chatStore.updateAssistantMessage(messageId, originalAssistantMessage);
          currentAbortController = null;
        },
      },
      abortSignal,
      chatStore.useRag,
      chatStore.forceThink,
      chatStore.searchMode,
      activeConversationId,
      [],
      { tutorProfile: latestState.tutorProfile },
    );
  } catch (error) {
    currentAbortController = null;
    const err = normalizeError(error);
    chatStore.setError(err);
    chatStore.endStreaming();
    chatStore.updateAssistantMessage(messageId, originalAssistantMessage);
    throw err;
  }
}

/**
 * Edit a user message and regenerate the AI response
 * Updates the user message content and removes subsequent AI messages,
 * then generates a new AI response based on the edited content
 * @param messageId - The user message ID to edit
 * @param newContent - The new content for the user message
 */
export async function editUserMessage(
  messageId: string,
  newContent: string
): Promise<void> {
  // Validate input
  validateMessageContent(newContent);
  const sanitizedContent = newContent.trim();

  // Cancel any ongoing stream
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }

  const chatStore = useChatStore.getState();
  const conversationStore = useConversationStore.getState();
  const shouldPersist = canPersistHistory();
  const messages = chatStore.messages;

  // Find the user message
  const messageIndex = messages.findIndex((msg) => msg.id === messageId);
  if (messageIndex === -1) {
    throw new Error('Message not found');
  }

  const targetMessage = messages[messageIndex];
  if (targetMessage.role !== 'user') {
    throw new Error('Can only edit user messages');
  }

  const activeConversationId = conversationStore.activeConversationId;
  if (!activeConversationId) {
    throw new Error('No active conversation');
  }

  // IMPORTANT: Build API messages array BEFORE any store updates to avoid timing issues
  // Use two-step approach to guarantee edited message is always included

  // Step 1: Build history messages (before the edited message) using shared filter function
  const historyMessages = prepareMessagesForAPI(
    messages.slice(0, messageIndex),
    undefined,
    activeConversationId
  );

  // Step 2: Always include the edited user message at the end
  const apiMessages: ChatMessage[] = [
    ...historyMessages,
    { role: 'user', content: `${sanitizedContent}${formatAttachmentContext(targetMessage.attachments)}` },
  ];

  const originalMessagesSnapshot = [...messages];
  const supersededMessages = messages.slice(messageIndex + 1);
  const supersededMessageIds = supersededMessages.map((msg) => msg.id);

  // Now perform optimistic store updates. Persistence is committed only after
  // the replacement assistant response completes, so failed edits can restore
  // the original branch without losing later turns.
  chatStore.updateMessageContent(messageId, sanitizedContent);
  for (const msg of supersededMessages) {
    chatStore.removeMessage(msg.id);
  }

  // 4. Create new abort controller for this request
  currentAbortController = new AbortController();
  const abortSignal = currentAbortController.signal;

  // 5. Add new assistant message placeholder
  const assistantMessageId = chatStore.addAssistantMessage(activeConversationId);

  // 6. Start streaming
  chatStore.startStreaming(assistantMessageId);

  // Track state for database save
  const latestState = useChatStore.getState();
  let thinkingContent = '';
  let thinkingStartTime: number | null = null;
  let answerContent = '';
  let citations: string[] = [];
  let sourcesPayload: CitationSource[] = [];
  let answerBlocksPayload: AnswerBlock[] = [];
  let suggestionsList: string[] = [];

  try {
    await createChatStream(
      apiMessages,
      {
        onThinkingStart: () => {
          // Hide the RAG panel at the first generation boundary. The first
          // thinking/content token may arrive after this callback, and backend
          // streams are not guaranteed to emit a separate `generating` status.
          chatStore.setRagStatus('generating');
          if (!latestState.forceThink) return;
          thinkingStartTime = Date.now();
        },

        onThinkingContent: (chunk: string) => {
          if (!latestState.forceThink) return;
          thinkingContent += chunk;
          chatStore.appendThinkingContent(chunk);
        },

        onThinkingEnd: () => {
          if (!latestState.forceThink) return;
          chatStore.endThinking();
        },

        onContent: (chunk: string) => {
          answerContent += chunk;
          chatStore.appendContent(chunk);
        },

        onCitations: (citationUrls: string[]) => {
          citations = citationUrls;
          chatStore.setCitations(citationUrls);
        },

        onStatus: (status: 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done', message: string) => {
          chatStore.setRagStatus(status, message);
        },

        onSources: (sources: CitationSource[]) => {
          sourcesPayload = sources;
          chatStore.setRagStatus('sources_ready');
          chatStore.setRagSources(sources);
        },

        onAnswerBlocks: (blocks: AnswerBlock[]) => {
          answerBlocksPayload = blocks;
          chatStore.setAnswerBlocks(blocks);
        },

        onImageSlot: (slot: StreamingImageSlot) => {
          chatStore.addImageSlot(slot);
        },

        onSuggestions: (suggestions: string[]) => {
          suggestionsList = suggestions;
          chatStore.updateAssistantMessage(assistantMessageId, { suggestions });
        },

        onDone: async (suggestions?: string[]) => {
          chatStore.endStreaming(
            sourcesPayload.length > 0 ? sourcesPayload : undefined,
            answerBlocksPayload.length > 0 ? answerBlocksPayload : undefined,
          );

          // Update message with final suggestions if received in done event
          if (suggestions && suggestions.length > 0) {
            suggestionsList = suggestions;
            chatStore.updateAssistantMessage(assistantMessageId, { suggestions });
          }

          // Calculate thinking duration
          const thinkingDuration = thinkingStartTime
            ? Date.now() - thinkingStartTime
            : undefined;

          // Save assistant message to database
          const messageData: Omit<Message, 'id' | 'conversationId' | 'createdAt' | 'userId'> = {
            role: 'assistant',
            content: answerContent,
          };

          if (thinkingContent) {
            messageData.reasoning = {
              content: thinkingContent,
              duration: thinkingDuration,
            };
          }

          if (citations.length > 0) {
            messageData.citations = citations;
          }

          if (sourcesPayload.length > 0) {
            messageData.sources = sourcesPayload;
          }

          const answerBlocksForPersistence = persistentAnswerBlocks(answerBlocksPayload);
          if (answerBlocksForPersistence) messageData.answerBlocks = answerBlocksForPersistence;

          if (suggestionsList.length > 0) {
            messageData.suggestions = suggestionsList;
          }

          if (shouldPersist) {
            await databaseService.message.update(messageId, {
              content: sanitizedContent,
              updatedAt: new Date(),
            });
            await databaseService.message.add(activeConversationId, {
              id: assistantMessageId,
              ...messageData,
            });
            if (supersededMessageIds.length > 0) {
              await databaseService.message.deleteManyByConversationId(
                activeConversationId,
                supersededMessageIds,
              );
            }
          }


          if (shouldPersist) updateConversationPreviewInStore(activeConversationId, answerContent);

          // Trigger title generation if this is the first assistant response
          if (shouldPersist && apiMessages.length === 1 && answerContent) {
            const titleMessages = [
              ...apiMessages,
              { role: 'assistant', content: answerContent }
            ];
            // Start title generation in background (streaming to store)
            useConversationStore.getState().generateTitle(activeConversationId, titleMessages);
          }

          // Clear abort controller reference
          currentAbortController = null;
        },

        onError: (error: Error) => {
          chatStore.setError(error);
          chatStore.endStreaming();
          currentAbortController = null;
        },
      },
      abortSignal,
      chatStore.useRag,
      chatStore.forceThink,
      chatStore.searchMode,
      activeConversationId,
      [],
      { tutorProfile: latestState.tutorProfile },
    );
  } catch (error) {
    currentAbortController = null;
    const err = normalizeError(error);
    chatStore.setError(err);
    chatStore.endStreaming();
    chatStore.setMessages(originalMessagesSnapshot);
    logger.warn('chat_user_message_edit_rolled_back', {
      component: 'chatService',
      conversationId: activeConversationId,
      messageId,
      removedMessageCount: supersededMessageIds.length,
      reason: err.name,
    });
    throw err;
  }
}

/**
 * Edit a completed assistant response without regenerating the turn.
 *
 * Args:
 *   messageId: Assistant message to update.
 *   newContent: User-authored Markdown that should replace the assistant text.
 *
 * Side Effects:
 *   Updates the in-memory chat transcript, replaces stale text blocks with
 *   the edited Markdown while preserving existing image blocks, updates the
 *   active conversation preview when this is the latest message, and persists
 *   the edited response for authenticated users. Logs only safe metadata,
 *   never message text.
 *
 * @throws ValidationError if the edited content is empty or too long.
 * @throws Error when the target message is missing, not an assistant reply, or
 * currently streaming.
 */
export async function editAssistantMessage(
  messageId: string,
  newContent: string
): Promise<void> {
  validateMessageContent(newContent, false, ASSISTANT_EDIT_MAX_CONTENT_LENGTH);
  const sanitizedContent = newContent.trim();

  const chatStore = useChatStore.getState();
  const message = chatStore.messages.find((item) => item.id === messageId);
  if (!message) {
    throw new Error('Message not found');
  }
  if (message.role !== 'assistant') {
    throw new Error('Can only edit assistant messages');
  }
  if (message.isStreaming || chatStore.currentStreamingId === message.id) {
    throw new Error('Cannot edit a streaming assistant message');
  }

  const editedAnswerBlocks = answerBlocksForEditedContent(sanitizedContent, message.answerBlocks);
  const hadAnswerBlocks = Boolean(message.answerBlocks?.length);

  if (message.content === sanitizedContent && !hadAnswerBlocks && !message.streamImageSlots?.length) {
    return;
  }

  const updatedMessage: Message = {
    ...message,
    content: sanitizedContent,
    answerBlocks: editedAnswerBlocks,
    updatedAt: new Date(),
  };

  if (canPersistHistory()) {
    await databaseService.message.update(messageId, {
      content: sanitizedContent,
      answerBlocks: editedAnswerBlocks,
      updatedAt: updatedMessage.updatedAt,
    });
    try {
      await useNotesStore.getState().syncNoteFromMessage(updatedMessage);
    } catch (error) {
      logger.warn('chat_assistant_message_note_sync_failed', {
        component: 'chatService',
        conversationId: message.conversationId,
        messageId,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  chatStore.updateAssistantMessage(messageId, {
    content: sanitizedContent,
    answerBlocks: editedAnswerBlocks,
    streamImageSlots: undefined,
    isStreaming: false,
    voicePlayback: undefined,
    updatedAt: updatedMessage.updatedAt,
  });
  patchConversationPreviewIfLatest(message, sanitizedContent);

  logger.info('chat_assistant_message_edited', {
    component: 'chatService',
    conversationId: message.conversationId,
    messageId,
    persisted: canPersistHistory(),
    preservedImageBlocks: editedAnswerBlocks?.filter((block) => block.type === 'image_block').length ?? 0,
    replacedTextBlocks: hadAnswerBlocks,
  });
}

/**
 * Export validation error for consumers
 */
export { ValidationError };
