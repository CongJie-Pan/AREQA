'use client';

/**
 * MessageList Component
 * Displays list of chat messages with auto-scroll
 * Respects user manual scrolling
 */

import React, { useRef, useEffect, useCallback } from 'react';
import Image from 'next/image';
import { ArrowDown } from 'lucide-react';
import { useChatStore, chatSelectors } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useNotesStore } from '@/store/notes';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { MessageItem } from './MessageItem';
import { useStyles } from './styles';
import { databaseService } from '@/services/database';
import { consumeSourceMessageFocus } from '@/utils/messageFocus';
import type { MessageFeedback, MessageFeedbackDetails } from '@/database/schema';

/** Scroll threshold in pixels from bottom to trigger auto-scroll */
const SCROLL_THRESHOLD = 30;
const EMPTY_STATE_TYPEWRITER_SPEED_MS = 34;
const EMPTY_STATE_BACKSPACE_SPEED_MS = 22;
const EMPTY_STATE_HOLD_MS = 5000;
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

export interface MessageListProps {
  /** Reserve scrollable space beneath the last message for the voice logo. */
  liveVoice?: boolean;
  /** Class name for styling */
  className?: string;
  /** Callback when regenerate button is clicked */
  onRegenerate?: (messageId: string) => void;
  /** Callback when edit is submitted for user messages */
  onEdit?: (messageId: string, newContent: string) => void;
  /** Callback when the bottom assistant turn should be deleted */
  onDeleteLatestTurn?: (assistantMessageId: string) => void;
  /** Callback when an assistant response should be saved as a note */
  onAddNote?: (assistantMessageId: string) => void;
  /** Callback when a suggested question is selected */
  onSelectSuggestion?: (question: string) => void;
}

/**
 * Subscribes to the browser reduced-motion media query.
 *
 * Args:
 *   onStoreChange: Callback React invokes when the media query result changes.
 *
 * Returns:
 *   Cleanup function that removes the media query listener.
 *
 * Side effects:
 *   Registers a browser media query listener when matchMedia is available.
 */
function subscribeToReducedMotion(onStoreChange: () => void) {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return () => undefined;
  }

  const mediaQuery = window.matchMedia(REDUCED_MOTION_QUERY);
  mediaQuery.addEventListener('change', onStoreChange);

  return () => {
    mediaQuery.removeEventListener('change', onStoreChange);
  };
}

/**
 * Reads whether the current browser asks interfaces to minimize motion.
 *
 * Returns:
 *   True when the reduced-motion media query currently matches.
 */
function getReducedMotionSnapshot() {
  return typeof window !== 'undefined'
    && Boolean(window.matchMedia?.(REDUCED_MOTION_QUERY).matches);
}

/**
 * Provides a stable server-side reduced-motion fallback.
 *
 * Returns:
 *   False so server-rendered empty states match the default client animation.
 */
function getServerReducedMotionSnapshot() {
  return false;
}

/**
 * Renders one rotating translated empty-state line with a typewriter reveal.
 *
 * Args:
 *   lines: Localized lines to rotate through.
 *   className: Optional CSS class for visual styling.
 *
 * Returns:
 *   A paragraph that types one line, pauses, backspaces it, and advances to the
 *   next line unless the user requests reduced motion.
 *
 * Side effects:
 *   Starts and clears browser timers while rotating the empty-state copy.
 */
function RotatingTypewriterLine({
  lines,
  className,
}: {
  lines: string[];
  className?: string;
}) {
  const [{ lineIndex, visibleLength, isDeleting }, setTypewriterState] = React.useState({
    lineIndex: 0,
    visibleLength: 0,
    isDeleting: false,
  });
  const shouldReduceMotion = React.useSyncExternalStore(
    subscribeToReducedMotion,
    getReducedMotionSnapshot,
    getServerReducedMotionSnapshot,
  );
  const currentText = lines[lineIndex] ?? '';
  const currentCharacters = React.useMemo(() => Array.from(currentText), [currentText]);

  useEffect(() => {
    if (shouldReduceMotion || currentText.length === 0) {
      return undefined;
    }

    const isFullyTyped = visibleLength >= currentCharacters.length;
    const delay = isDeleting
      ? EMPTY_STATE_BACKSPACE_SPEED_MS
      : isFullyTyped
        ? EMPTY_STATE_HOLD_MS
        : EMPTY_STATE_TYPEWRITER_SPEED_MS;

    const timer = window.setTimeout(() => {
      setTypewriterState((previous) => {
        const activeText = lines[previous.lineIndex] ?? '';
        const activeCharactersLength = Array.from(activeText).length;

        if (!previous.isDeleting && previous.visibleLength >= activeCharactersLength) {
          return { ...previous, isDeleting: true };
        }

        if (previous.isDeleting && previous.visibleLength <= 0) {
          return {
            lineIndex: (previous.lineIndex + 1) % lines.length,
            visibleLength: 0,
            isDeleting: false,
          };
        }

        return {
          ...previous,
          visibleLength: previous.visibleLength + (previous.isDeleting ? -1 : 1),
        };
      });
    }, delay);

    return () => {
      window.clearTimeout(timer);
    };
  }, [currentCharacters.length, currentText.length, isDeleting, lines, shouldReduceMotion, visibleLength]);

  const renderedText = shouldReduceMotion
    ? lines[0] ?? ''
    : currentCharacters.slice(0, visibleLength).join('');
  const ariaLabel = shouldReduceMotion ? lines[0] ?? '' : currentText;

  return (
    <p className={className} aria-label={ariaLabel} aria-live="polite">
      <span aria-hidden="true">{renderedText}</span>
      {!shouldReduceMotion && <span className="areqa-empty-typewriter-cursor" aria-hidden="true" />}
    </p>
  );
}

/**
 * MessageList displays all messages in the current conversation
 */
export function MessageList({
  className,
  liveVoice = false,
  onRegenerate,
  onEdit,
  onDeleteLatestTurn,
  onAddNote,
  onSelectSuggestion,
}: MessageListProps) {
  const { styles, cx } = useStyles();
  const { t } = useUserPreferences();
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const lastScrollTopRef = useRef(0);
  const [showScrollButton, setShowScrollButton] = React.useState(false);
  const [focusedSourceMessageId, setFocusedSourceMessageId] = React.useState<string | null>(null);

  // Get state from store
  const messages = useChatStore(chatSelectors.displayMessages);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const currentStreamingId = useChatStore((state) => state.currentStreamingId);
  const thinkingContent = useChatStore((state) => state.thinkingContent);
  const isThinking = useChatStore((state) => state.isThinking);

  // RAG States
  const ragStatus = useChatStore((state) => state.ragStatus);
  const ragMessage = useChatStore((state) => state.ragMessage);
  const ragSources = useChatStore((state) => state.ragSources);
  const setMessageFeedback = useChatStore((state) => state.setMessageFeedback);
  const savedNotes = useNotesStore((state) => state.notes);
  const activeConversationId = useConversationStore((state) => state.activeConversationId);
  const isMessageHandoffLoading = useConversationStore((state) => state.isMessageHandoffLoading);
  const savedMessageIds = React.useMemo(
    () => new Set(savedNotes.map((note) => note.messageId).filter(Boolean)),
    [savedNotes],
  );

  const pauseAutoScrollForManualIntent = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const canScroll = container.scrollHeight > container.clientHeight;
    if (!canScroll) return;

    lastScrollTopRef.current = container.scrollTop;
    userScrolledUpRef.current = true;
    setShowScrollButton(true);
  }, []);

  const handleFeedback = useCallback(async (
    messageId: string,
    feedback: MessageFeedback | null,
    details: MessageFeedbackDetails = {}
  ) => {
    const currentMessage = useChatStore
      .getState()
      .messages
      .find((message) => message.id === messageId);
    const previousFeedback = currentMessage?.feedback ?? null;
    const previousDetails = {
      reason: currentMessage?.feedbackReason ?? null,
      comment: currentMessage?.feedbackComment ?? null,
    };

    setMessageFeedback(messageId, feedback, details);

    try {
      await databaseService.message.updateFeedback(messageId, feedback, details);
    } catch (error) {
      setMessageFeedback(messageId, previousFeedback, previousDetails);
      throw error;
    }
  }, [setMessageFeedback]);

  // Handle user scroll - track if user manually scrolled up
  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const previousScrollTop = lastScrollTopRef.current;
    const currentScrollTop = container.scrollTop;
    const isScrollingDown = currentScrollTop > previousScrollTop + 1;
    lastScrollTopRef.current = currentScrollTop;

    // Detect if we are at the bottom with a small buffer
    const isAtBottom = 
      container.scrollHeight - currentScrollTop - container.clientHeight < 10;

    if (isAtBottom && (!userScrolledUpRef.current || isScrollingDown)) {
      // User is at bottom - allow auto-scroll
      userScrolledUpRef.current = false;
      setShowScrollButton(false);
    } else {
      // User scrolled up - stop auto-scroll
      userScrolledUpRef.current = true;
      setShowScrollButton(true);
    }
  }, []);

  // Add scroll event listener
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  // Reset user scroll state when streaming starts (if already at bottom)
  useEffect(() => {
    if (isStreaming) {
      const container = containerRef.current;
      if (container) {
        // Only resume bottom-following when the user has not already expressed
        // manual scroll intent during the same turn.
        const isAtBottom =
          container.scrollHeight - container.scrollTop - container.clientHeight < SCROLL_THRESHOLD;
        
        if (isAtBottom && !userScrolledUpRef.current) {
          userScrolledUpRef.current = false;
          setTimeout(() => setShowScrollButton(false), 0);
        }
      }
    }
  }, [isStreaming]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (containerRef.current) {
      const container = containerRef.current;

      requestAnimationFrame(() => {
        // Manual scroll intent wins over the near-bottom heuristic. This keeps
        // streaming answers draggable instead of snapping back to the bottom
        // while the user is trying to inspect earlier text.
        const shouldAutoScroll = !userScrolledUpRef.current;

        if (shouldAutoScroll) {
          container.scrollTo({
            top: Math.max(0, container.scrollHeight - container.clientHeight),
            behavior: isStreaming ? 'auto' : 'smooth',
          });
        }
      });
    }
  }, [messages, isStreaming, thinkingContent, liveVoice]);

  // Scroll to bottom button click handler
  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      userScrolledUpRef.current = false;
      setShowScrollButton(false);
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, []);

  useEffect(() => {
    if (!activeConversationId || messages.length === 0) return;

    const sourceMessageId = consumeSourceMessageFocus(activeConversationId);
    if (!sourceMessageId) return;

    let clearHighlightTimer: number | null = null;
    const frameId = requestAnimationFrame(() => {
      const container = containerRef.current;
      const sourceElement = Array.from(
        container?.querySelectorAll<HTMLElement>('[data-message-id]') ?? [],
      ).find((element) => element.dataset.messageId === sourceMessageId);

      if (!sourceElement) return;

      userScrolledUpRef.current = true;
      sourceElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setFocusedSourceMessageId(sourceMessageId);

      if (container) {
        const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
        setShowScrollButton(distanceToBottom >= 10);
      }

      clearHighlightTimer = window.setTimeout(() => {
        setFocusedSourceMessageId((currentMessageId) => (
          currentMessageId === sourceMessageId ? null : currentMessageId
        ));
      }, 2800);
    });

    return () => {
      cancelAnimationFrame(frameId);
      if (clearHighlightTimer) window.clearTimeout(clearHighlightTimer);
    };
  }, [activeConversationId, messages]);

  if (messages.length === 0 && isMessageHandoffLoading) {
    // Keep the transcript quiet while a saved conversation is loading. Rendering
    // the empty-state hero here causes a visible new-chat flash during switches.
    // This uses a dedicated handoff flag so normal conversation-list loading
    // never hides the intentional new-chat screen.
    return (
      <div
        aria-busy="true"
        className={cx('areqa-message-list', 'areqa-message-list-non-empty', styles.container, styles.nonEmpty, className)}
      />
    );
  }

  // Show empty state
  if (messages.length === 0) {
    const emptyStateLines = [
      t('emptyStateGreeting'),
      t('emptyStateLearningPrompt'),
      t('emptyStateTutorPrompt'),
    ];

    return (
      <div className={cx('areqa-message-list', 'areqa-message-list-empty', styles.container, styles.empty, className)}>
        <div className={cx('areqa-message-empty-logo-stage', styles.emptyLogoStage)}>
          <Image
            src="/icon/areqa_icon_v4_circle.png"
            alt="AREQA Logo"
            width={128}
            height={128}
            unoptimized
            className={cx('areqa-message-empty-logo', styles.emptyLogo)}
            draggable={false}
            priority
          />
        </div>
        <div className={cx('areqa-message-empty-copy', styles.emptyCopy)}>
          <RotatingTypewriterLine
            key={emptyStateLines.join('\u0000')}
            lines={emptyStateLines}
            className={cx('areqa-message-empty-subtitle', styles.emptySubtitle)}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={cx('areqa-message-list-viewport', styles.viewport, className)}>
      <div
        ref={containerRef}
        onWheel={pauseAutoScrollForManualIntent}
        onTouchMove={pauseAutoScrollForManualIntent}
        className={cx(
          'areqa-message-list',
          'areqa-message-list-non-empty',
          styles.container,
          styles.nonEmpty,
          liveVoice && styles.containerLiveVoice,
        )}
      >
        {messages.map((message, index) => {
          const isCurrentStreaming = message.id === currentStreamingId;
          const isLast = index === messages.length - 1;

          // Detect if this is an assistant message following a user message
          const isAssistantAfterUser =
            message.role === 'assistant' &&
            index > 0 &&
            messages[index - 1].role === 'user';

          return (
            <MessageItem
              key={message.id}
              message={message}
              isStreaming={Boolean(message.isStreaming || (isCurrentStreaming && isStreaming))}
              isLast={isLast}
              className={cx(
                isAssistantAfterUser && 'assistant-after-user',
                message.id === focusedSourceMessageId && styles.sourceFocusedMessage,
              )}
              onSelectSuggestion={onSelectSuggestion}
              thinking={
                isCurrentStreaming
                  ? {
                      content: thinkingContent,
                      isThinking,
                    }
                  : undefined
              }
              ragInfo={
                isCurrentStreaming && isStreaming
                  ? {
                      status: ragStatus,
                      message: ragMessage,
                      sources: ragSources,
                    }
                  : undefined
              }
              onRegenerate={message.role === 'assistant' ? onRegenerate : undefined}
              onAddNote={message.role === 'assistant' && !isStreaming ? onAddNote : undefined}
              isSavedNote={message.role === 'assistant' ? savedMessageIds.has(message.id) : false}
              onDeleteLatestTurn={
                message.role === 'assistant' && isLast && !isStreaming
                  ? onDeleteLatestTurn
                  : undefined
              }
              onFeedback={
                message.role === 'assistant' && message.userId !== 'guest'
                  ? handleFeedback
                  : undefined
              }
              onEdit={message.role === 'user' ? onEdit : undefined}
            />
          );
        })}

        {liveVoice ? (
          <div className={styles.voiceSpacer} aria-hidden="true" />
        ) : (
          <div className={cx('areqa-message-scroll-spacer', styles.scrollButtonSpacer)} aria-hidden="true" />
        )}
      </div>

      {/* Keep this control outside the scrollable content so it remains visible after the user scrolls up. */}
      {showScrollButton && (
        <button
          className={cx('areqa-message-scroll-button', styles.scrollButton)}
          onClick={scrollToBottom}
          aria-label="滑動到底部"
          type="button"
        >
          <ArrowDown size={20} />
        </button>
      )}
    </div>
  );
}

export default MessageList;
export { MessageItem } from './MessageItem';
