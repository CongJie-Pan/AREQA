'use client';

/**
 * ChatContainer Component
 * Main container that assembles the complete chat interface
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import { PanelLeftOpen, PanelLeftClose, X, AlertCircle, MoreHorizontal, FileText, FileImage, FileCode, Share2 } from 'lucide-react';
import { App, Dropdown } from 'antd';
import { exportToMarkdown, exportToDocx, exportToPdf } from '@/utils/exportChat';
import { useChatStore, chatSelectors } from '@/store/chat';
import { useConversationStore, conversationSelectors } from '@/store/conversation';
import { sendMessage, initializeChatService, cancelCurrentStream, regenerateMessage, editUserMessage, editAssistantMessage, deleteLatestConversationTurn } from '@/services/chat';
import { ConversationList } from '@/components/ConversationList';
import { MessageList } from '@/components/MessageList';
import { ImageGenerationLoading } from '@/components/MessageList/ImageGenerationLoading';
import { ChatInput } from '@/components/ChatInput';
import { TextSelectionToolbar } from '@/components/TextSelectionToolbar';
import { GumPanel } from '@/components/GumPanel';
import { MailboxPanel } from '@/components/MailboxPanel';
import { NotesPanel } from '@/components/NotesPanel';
import { ProactiveManager } from '@/components/ProactiveManager';
import { AuthPrompt } from '@/components/Auth';
import { LiveTutorPanel } from '@/components/LiveTutor';
import { supabase } from '@/lib/supabase';
import { initializeAuth, useAuthStore } from '@/store/auth';
import { useFeatureStore } from '@/store/features';
import { useLiveTutorStore } from '@/store/liveTutor';
import { useNotesStore } from '@/store/notes';
import { syncService } from '@/services/syncService';
import { databaseService } from '@/services/database';
import { db } from '@/database/db';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { cancelConversationImage, generateConversationImage } from '@/services/generatedImages';
import { useStyles } from './styles';
import { useSidebarResize } from './useSidebarResize';
import { useSidebarState } from './useSidebarState';
import { LongConversationReminder } from './LongConversationReminder';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';

/**
 * Error type classification for user-friendly messages
 */
function getErrorMessage(error: unknown): { message: string; isRetryable: boolean } {
  const errorMessage = error instanceof Error ? error.message : String(error);
  const lowerMessage = errorMessage.toLowerCase();

  if (lowerMessage.includes('network') || lowerMessage.includes('fetch') || lowerMessage.includes('connection')) {
    return {
      message: '網路連線錯誤。請確認您的網路狀況後再試一次。',
      isRetryable: true,
    };
  }

  if (lowerMessage.includes('rate limit') || lowerMessage.includes('429')) {
    return {
      message: '請求太頻繁。請稍候再試。',
      isRetryable: true,
    };
  }

  if (lowerMessage.includes('unauthorized') || lowerMessage.includes('401') || lowerMessage.includes('api key')) {
    return {
      message: '驗證失敗。請檢查您的 API 密鑰設定。',
      isRetryable: false,
    };
  }

  if (lowerMessage.includes('timeout')) {
    return {
      message: '請求超時。請再試一次。',
      isRetryable: true,
    };
  }

  return {
    message: `發送訊息失敗：${errorMessage}`,
    isRetryable: true,
  };
}

export interface ChatContainerProps {
  /** Class name for styling */
  className?: string;
}
import { SidePanelType } from '@/types/panel';

const AVATAR_PANE_DEFAULT_WIDTH = 320;
const AVATAR_PANE_MIN_WIDTH = 260;
const AVATAR_PANE_MAX_WIDTH = 420;
const RESPONSE_PANE_MIN_WIDTH = 420;


/**
 * ChatContainer is the main component that assembles the chat interface
 */
export function ChatContainer({ className }: ChatContainerProps) {
  const { styles, cx } = useStyles();
  const { message: antMessageApi } = App.useApp();
  const { t, language } = useUserPreferences();
  const {
    isOpen: sidebarOpen, isMobile, desktopCollapsed, mobileOpen,
    toggle: toggleSidebar, closeMobile: closeSidebar,
  } = useSidebarState();
  const sidebarId = React.useId();
  const sidebarResize = useSidebarResize();
  const sidebarWidth = sidebarResize.width;
  const stopSidebarResize = sidebarResize.stopResize;
  useEffect(() => { stopSidebarResize(); }, [sidebarOpen, stopSidebarResize]);
  const [gumPanelType, setGumPanelType] = useState<SidePanelType>(null);
  const [showAuthPrompt, setShowAuthPrompt] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [isChatReady, setIsChatReady] = useState(false);
  const [avatarPaneWidth, setAvatarPaneWidth] = useState(AVATAR_PANE_DEFAULT_WIDTH);
  const avatarResizeStateRef = useRef<{
    startX: number;
    startWidth: number;
  } | null>(null);
  const mailboxEnabled = useFeatureStore((state) => state.mailbox);
  const compeerEnabled = useFeatureStore((state) => state.compeer);
  const fetchFeatures = useFeatureStore((state) => state.fetchFeatures);
  const user = useAuthStore((state) => state.user);
  const historyUserId = user?.id ?? null;
  const previousHistoryUserIdRef = useRef(historyUserId);
  const failedMessageSyncCount = useLiveQuery(
    () => user
      ? db.messageSyncQueue.where('userId').equals(user.id)
          .filter((row) => Boolean(row.lastError)).count()
      : Promise.resolve(0),
    [user?.id],
    0,
  );
  const isAuthInitialized = useAuthStore((state) => state.isInitialized);
  const validateSession = useAuthStore((state) => state.validateSession);
  const addNoteFromMessage = useNotesStore((state) => state.addNoteFromMessage);
  const loadNotes = useNotesStore((state) => state.loadNotes);

  useEffect(() => {
    if (failedMessageSyncCount > 0) {
      antMessageApi.open({
        type: 'warning',
        key: 'history-sync-pending',
        content: t('historySyncPending'),
        duration: 0,
      });
    } else {
      antMessageApi.destroy('history-sync-pending');
    }
    return () => antMessageApi.destroy('history-sync-pending');
  }, [antMessageApi, failedMessageSyncCount, t]);

  // Get state from stores
  const isStreaming = useChatStore((state) => state.isStreaming);
  const imageGenerationRequests = useChatStore((state) => state.imageGenerationRequests);
  const error = useChatStore((state) => state.error);
  const setError = useChatStore((state) => state.setError);
  const messages = useChatStore(chatSelectors.displayMessages);
  const openLiveTutor = useLiveTutorStore((state) => state.open);
  const isLiveTutorOpen = useLiveTutorStore((state) => state.isOpen);
  const isLiveTutorMuted = useLiveTutorStore((state) => state.isMuted);
  const isLiveTutorAvatarEnabled = useLiveTutorStore((state) => state.avatarEnabled);
  const setLiveTutorMuted = useLiveTutorStore((state) => state.setMuted);
  const setLiveTutorAvatarEnabled = useLiveTutorStore((state) => state.setAvatarEnabled);
  const requestCloseLiveTutor = useLiveTutorStore((state) => state.requestClose);
  const isEmpty = messages.length === 0;
  const isEmptyLiveTutor = isLiveTutorOpen && isEmpty;
  const useAvatarSplitLayout = isLiveTutorOpen && isLiveTutorAvatarEnabled && !gumPanelType;
  const hideLiveTutorMessages = isEmptyLiveTutor && !useAvatarSplitLayout;

  const activeConversation = useConversationStore((state) =>
    conversationSelectors.activeConversation(state)
  );
  const activeConversationId = useConversationStore(
    (state) => state.activeConversationId
  );
  const activeImageRequest = Object.values(imageGenerationRequests ?? {}).find((request) => (
    request.userId === user?.id && request.conversationId === activeConversationId
  ));
  const isGeneratingImage = Boolean(activeImageRequest);
  const isMessageHandoffLoading = useConversationStore((state) => state.isMessageHandoffLoading);
  const shouldShowEmptyChat = isEmpty && !isMessageHandoffLoading && !isGeneratingImage;
  const landingPromptSent = useRef(false);

  const toggleLiveTutorMute = useCallback(() => {
    setLiveTutorMuted(!useLiveTutorStore.getState().isMuted);
  }, [setLiveTutorMuted]);

  const toggleLiveTutorAvatar = useCallback(() => {
    setLiveTutorAvatarEnabled(!useLiveTutorStore.getState().avatarEnabled);
  }, [setLiveTutorAvatarEnabled]);

  useEffect(() => {
    void fetchFeatures();
  }, [fetchFeatures]);

  useEffect(() => {
    if (!mailboxEnabled && gumPanelType === 'mailbox') {
      setGumPanelType(null);
    }
  }, [gumPanelType, mailboxEnabled]);

  useEffect(() => {
    const viewport = window.visualViewport;
    const root = document.documentElement;
    let animationFrameId: number | null = null;

    const updateViewportHeight = () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }

      animationFrameId = window.requestAnimationFrame(() => {
        const viewportHeight = viewport?.height ?? window.innerHeight;
        const viewportTop = viewport?.offsetTop ?? 0;
        root.style.setProperty(
          '--areqa-visual-viewport-height',
          `${Math.round(viewportHeight)}px`,
        );
        root.style.setProperty(
          '--areqa-visual-viewport-top',
          `${Math.round(viewportTop)}px`,
        );
        animationFrameId = null;
      });
    };

    updateViewportHeight();
    viewport?.addEventListener('resize', updateViewportHeight);
    viewport?.addEventListener('scroll', updateViewportHeight);
    window.addEventListener('resize', updateViewportHeight);
    window.addEventListener('orientationchange', updateViewportHeight);
    window.addEventListener('focus', updateViewportHeight);
    window.addEventListener('pageshow', updateViewportHeight);
    document.addEventListener('visibilitychange', updateViewportHeight);

    return () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }
      viewport?.removeEventListener('resize', updateViewportHeight);
      viewport?.removeEventListener('scroll', updateViewportHeight);
      window.removeEventListener('resize', updateViewportHeight);
      window.removeEventListener('orientationchange', updateViewportHeight);
      window.removeEventListener('focus', updateViewportHeight);
      window.removeEventListener('pageshow', updateViewportHeight);
      document.removeEventListener('visibilitychange', updateViewportHeight);
      root.style.removeProperty('--areqa-visual-viewport-height');
      root.style.removeProperty('--areqa-visual-viewport-top');
    };
  }, []);

  // Resolve authentication before loading any user-owned history.
  useEffect(() => {
    void initializeAuth();
  }, []);

  useEffect(() => {
    const validateWhenVisible = () => {
      if (document.visibilityState === 'visible') void validateSession();
    };

    document.addEventListener('visibilitychange', validateWhenVisible);
    window.addEventListener('focus', validateWhenVisible);

    return () => {
      document.removeEventListener('visibilitychange', validateWhenVisible);
      window.removeEventListener('focus', validateWhenVisible);
    };
  }, [validateSession]);

  useEffect(() => {
    if (!isAuthInitialized) return;

    let cancelled = false;
    setIsChatReady(false);

    const accountChanged = previousHistoryUserIdRef.current !== historyUserId;
    previousHistoryUserIdRef.current = historyUserId;
    if (accountChanged && historyUserId) {
      // Never retain the previous account's visible history during a refresh.
      useConversationStore.getState().clearState();
      useChatStore.getState().clearMessages();
      useChatStore.getState().resetStreamingState();
      useNotesStore.setState({ notes: [], loading: false, error: null });
    }
    logger.info('chat_history_initialization_started', {
      component: 'ChatContainer',
      reason: accountChanged ? 'account_changed' : 'auth_ready',
      authenticated: Boolean(historyUserId),
    });

    const loadAuthenticatedHistory = async () => {
      if (!historyUserId) {
        useConversationStore.getState().clearState();
        useChatStore.getState().clearMessages();
        useChatStore.getState().resetStreamingState();
        useNotesStore.setState({ notes: [], loading: false, error: null });
        if (typeof indexedDB !== 'undefined') {
          try {
            await databaseService.conversation.clearGuestData();
            await databaseService.note.clearGuestData();
          } catch (error) {
            console.error('Failed to clear legacy guest history:', error);
          }
        }
        if (!cancelled) setIsChatReady(true);
        return;
      }

      try {
        setShowAuthPrompt(false);
        const localLoadStartedAt = performance.now();
        await initializeChatService(historyUserId);
        if (cancelled) return;
        await loadNotes(historyUserId);
        if (cancelled) return;
        logger.info('chat_history_local_cache_loaded', {
          component: 'ChatContainer',
          durationMs: Math.round(performance.now() - localLoadStartedAt),
          source: 'dexie',
        });
        if (!cancelled) setIsChatReady(true);

        const cloudSyncStartedAt = performance.now();
        void syncService.pullFromCloud(historyUserId)
          .then(async () => {
            if (cancelled) return;
            await initializeChatService(historyUserId);
            if (cancelled) return;
            await loadNotes(historyUserId);
            if (cancelled) return;
            logger.info('chat_history_cloud_sync_finished', {
              component: 'ChatContainer',
              durationMs: Math.round(performance.now() - cloudSyncStartedAt),
              refreshedConversationStore: true,
              refreshedNotesStore: true,
            });
          })
          .catch((syncError) => {
            logger.error(
              'chat_history_cloud_sync_unhandled_error',
              syncError instanceof Error ? syncError : new Error(String(syncError)),
              { component: 'ChatContainer' },
            );
          });
      } catch (error) {
        console.error('Failed to initialize authenticated history:', error);
      } finally {
        if (!cancelled) setIsChatReady(true);
      }
    };

    void loadAuthenticatedHistory();

    return () => {
      cancelled = true;
    };
  }, [isAuthInitialized, loadNotes, historyUserId]);

  // Load messages when conversation changes
  useEffect(() => {
    if (!activeConversationId) {
      // Clear messages when no conversation is active
      useChatStore.getState().clearMessages();
      useChatStore.getState().resetStreamingState();
    }
    useChatStore.getState().setQuotedText(null);
    // Note: We don't call loadMessages(activeConversationId) here because
    // it's already handled by switchConversation() and sendMessage()
    // calls. Calling it here causes a race condition that clears
    // the streaming state for new conversations.
  }, [activeConversationId]);

  // Handle sending message with improved error handling
  const handleSend = useCallback(
    async function retryableSend(content: string, attachments: File[] = [], options: { createImage?: boolean } = {}) {
      try {
        if (options.createImage) {
          if (!user) {
            setShowAuthPrompt(true);
            return { completed: false };
          }
          return await generateConversationImage(content, activeConversationId || undefined, language, true, { attachments });
        }
        const voiceMessage = useLiveTutorStore.getState().isOpen;
        const result = voiceMessage
          ? await (useLiveTutorStore.getState().sendVoiceMessage?.(content, attachments)
            ?? Promise.reject(new Error('Voice message is not ready')))
          : await sendMessage(content, activeConversationId || undefined, attachments);
        if (voiceMessage && attachments.length > 0 && result.completed) antMessageApi.success('附件已可供語音使用');
        if (result?.completed) {
          const { data: { session } } = await supabase.auth.getSession();
          if (!session) setShowAuthPrompt(true);
        }
        return result;
      } catch (err) {
        logger.warn('message_send_failed', { reason: err instanceof Error ? err.name : 'UnknownError' });

        // Get user-friendly error message
        const { message: errorMsg, isRetryable } = getErrorMessage(err);

        // Show appropriate notification
        if (isRetryable) {
          antMessageApi.error({
            content: (
              <span>
                {errorMsg}
                <button
                  onClick={() => {
                    antMessageApi.destroy('send-error');
                    void retryableSend(content, attachments, options).catch(() => undefined); // Retry with the same request
                  }}
                  style={{
                    marginLeft: '12px',
                    padding: '2px 8px',
                    background: 'transparent',
                    border: '1px solid currentColor',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '12px',
                  }}
                >
                  {t('retry')}
                </button>
              </span>
            ),
            duration: 8,
            key: 'send-error',
          });
        } else {
          antMessageApi.error({
            content: errorMsg,
            duration: 5,
            key: 'send-error',
          });
        }

        throw err;
      }
    },
    [activeConversationId, antMessageApi, language, t, user]
  );

  // A prompt supplied by the landing page starts a new chat automatically.
  // Remove it from the address bar first so refreshing the page never resends it.
  useEffect(() => {
    if (!isChatReady || landingPromptSent.current) return;

    const url = new URL(window.location.href);
    const prompt = url.searchParams.get('prompt')?.trim();
    if (!prompt) return;

    landingPromptSent.current = true;
    url.searchParams.delete('prompt');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);

    void handleSend(prompt).catch(() => undefined);
  }, [handleSend, isChatReady]);

  // Handle conversation selection
  const handleConversationSelect = useCallback(() => {
    closeSidebar();
    setGumPanelType(null); // Return to chat view
  }, [closeSidebar]);

  // Handle new conversation
  const handleNewConversation = useCallback(() => {
    // Just clear UI state and deselect active conversation
    useConversationStore.getState().clearActiveConversation();
    useChatStore.getState().clearMessages();
    useChatStore.getState().resetStreamingState();
    closeSidebar();
    setGumPanelType(null); // Return to chat view
  }, [closeSidebar]);

  const resizeAvatarPane = useCallback((event: PointerEvent) => {
    const resizeState = avatarResizeStateRef.current;
    if (!resizeState) return;

    const availableWidth = Math.max(window.innerWidth - (!isMobile && sidebarOpen ? sidebarWidth : 0), 0);
    const minAvatarWidth = AVATAR_PANE_MIN_WIDTH;
    const maxAvatarWidth = Math.max(
      minAvatarWidth,
      Math.min(AVATAR_PANE_MAX_WIDTH, availableWidth - RESPONSE_PANE_MIN_WIDTH),
    );
    const nextWidth = resizeState.startWidth + resizeState.startX - event.clientX;
    setAvatarPaneWidth(Math.min(Math.max(nextWidth, minAvatarWidth), maxAvatarWidth));
  }, [isMobile, sidebarOpen, sidebarWidth]);

  const stopAvatarPaneResize = useCallback(() => {
    avatarResizeStateRef.current = null;
    document.body.style.removeProperty('cursor');
    document.body.style.removeProperty('user-select');
    window.removeEventListener('pointermove', resizeAvatarPane);
    window.removeEventListener('pointerup', stopAvatarPaneResize);
    window.removeEventListener('pointercancel', stopAvatarPaneResize);
  }, [resizeAvatarPane]);

  const startAvatarPaneResize = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    avatarResizeStateRef.current = {
      startX: event.clientX,
      startWidth: avatarPaneWidth,
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', resizeAvatarPane);
    window.addEventListener('pointerup', stopAvatarPaneResize);
    window.addEventListener('pointercancel', stopAvatarPaneResize);
  }, [avatarPaneWidth, resizeAvatarPane, stopAvatarPaneResize]);

  const handleAvatarResizeKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    setAvatarPaneWidth((currentWidth) => {
      const delta = event.key === 'ArrowLeft' ? 24 : -24;
      return Math.min(Math.max(currentWidth + delta, AVATAR_PANE_MIN_WIDTH), AVATAR_PANE_MAX_WIDTH);
    });
  }, []);

  useEffect(() => stopAvatarPaneResize, [stopAvatarPaneResize]);

  // Dismiss error
  const dismissError = useCallback(() => {
    setError(null);
  }, [setError]);

  const dismissAuthPrompt = useCallback(() => {
    setShowAuthPrompt(false);
  }, []);

  // Image cancellation must not interrupt the independently owned voice/text stream.
  const handleStop = useCallback(async () => {
    if (cancelConversationImage(activeConversationId) || isGeneratingImage) return;
    await cancelCurrentStream();
  }, [activeConversationId, isGeneratingImage]);

  // Handle regenerate message
  const handleRegenerate = useCallback(async (messageId: string) => {
    try {
      await regenerateMessage(messageId);
    } catch (err) {
      console.error('Failed to regenerate message:', err);
      antMessageApi.error('重新生成失敗，請稍後再試');
    }
  }, [antMessageApi]);

  // Handle edit message
  const handleEdit = useCallback(async (messageId: string, newContent: string) => {
    const targetMessage = useChatStore.getState().messages.find((message) => message.id === messageId);
    try {
      if (targetMessage?.role === 'assistant') {
        await editAssistantMessage(messageId, newContent);
      } else {
        await editUserMessage(messageId, newContent);
      }
    } catch (err) {
      console.error('Failed to edit message:', err);
      const imageCode = err instanceof Error ? err.message.match(/IMAGE_[A-Z0-9_]+/)?.[0] : undefined;
      antMessageApi.error(imageCode ? `產圖失敗（${imageCode}）` : '編輯訊息失敗，請稍後再試');
      throw err;
    }
  }, [antMessageApi]);

  const handleDeleteLatestTurn = useCallback(async (assistantMessageId: string) => {
    try {
      await deleteLatestConversationTurn(assistantMessageId);
      antMessageApi.success(t('deleteLatestConversationTurnSuccess'));
    } catch (err) {
      console.error('Failed to delete latest conversation turn:', err);
      antMessageApi.error(t('deleteLatestConversationTurnFailed'));
    }
  }, [antMessageApi, t]);

  const handleAddNote = useCallback(async (messageId: string) => {
    const sourceMessage = useChatStore.getState().messages.find((message) => message.id === messageId);
    if (!sourceMessage || sourceMessage.role !== 'assistant') {
      antMessageApi.error(t('addNoteFailed'));
      return;
    }

    try {
      await addNoteFromMessage(sourceMessage, activeConversation?.title ?? null);
      antMessageApi.success(t('addedToNotes'));
    } catch (err) {
      console.error('Failed to add note:', err);
      antMessageApi.error(t('addNoteFailed'));
    }
  }, [activeConversation?.title, addNoteFromMessage, antMessageApi, t]);

  const handleShareConversation = useCallback(async () => {
    if (!user) {
      antMessageApi.warning(t('shareLoginRequired'));
      setShowAuthPrompt(true);
      return;
    }

    if (!activeConversation || messages.length === 0) {
      antMessageApi.warning(t('shareNoConversation'));
      return;
    }

    setIsSharing(true);
    try {
      const response = await authenticatedFetch(`/api/share/conversations/${activeConversation.id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          conversation: activeConversation,
          messages,
        }),
      });

      const payload = await response.json().catch(() => null) as { token?: string; error?: string } | null;
      if (!response.ok || !payload?.token) {
        throw new Error(payload?.error || `Share API did not return a token (${response.status})`);
      }

      const shareUrl = `${window.location.origin}/share/${payload.token}`;
      try {
        await navigator.clipboard.writeText(shareUrl);
        antMessageApi.success(t('shareLinkCopied'));
      } catch (clipboardError) {
        console.warn('Created share link but could not copy it to clipboard:', clipboardError);
        antMessageApi.info({
          content: (
            <span>
              {t('shareLinkCreated')}
              <a href={shareUrl} target="_blank" rel="noopener noreferrer">
                {shareUrl}
              </a>
            </span>
          ),
          duration: 12,
        });
      }
    } catch (error) {
      console.error('Failed to share conversation:', error);
      const reason = error instanceof Error ? error.message : '';
      antMessageApi.error(reason ? `${t('shareLinkFailed')} ${reason}` : t('shareLinkFailed'));
    } finally {
      setIsSharing(false);
    }
  }, [activeConversation, antMessageApi, messages, t, user]);

  return (
    <div className={cx('areqa-chat-shell', styles.container, className)}>
      {/* Sidebar Overlay (mobile) */}
      {mobileOpen && (
        <div className={styles.sidebarOverlay} onClick={closeSidebar} />
      )}

      {/* Sidebar */}
      <div
        id={sidebarId}
        aria-hidden={!sidebarOpen}
        inert={!sidebarOpen}
        className={cx('areqa-chat-sidebar', styles.sidebar, mobileOpen && styles.sidebarOpen, desktopCollapsed && styles.sidebarCollapsed)}
        style={{ '--areqa-sidebar-width': `${sidebarWidth}px` } as React.CSSProperties}
      >
        <ConversationList
          onSelect={handleConversationSelect}
          onNew={handleNewConversation}
          externalSidebarToggle
          onSelectGumPanel={(type) => {
            setGumPanelType(type);
            closeSidebar(); // Close sidebar on mobile when opening panel
          }}
        />
        {sidebarOpen && (
          <div
            className={styles.sidebarResizeHandle}
            role="separator"
            aria-label={t('resizeSidebar')}
            aria-orientation="vertical"
            aria-valuemin={sidebarResize.minWidth}
            aria-valuemax={sidebarResize.maxWidth}
            aria-valuenow={sidebarWidth}
            tabIndex={0}
            onPointerDown={sidebarResize.startResize}
            onKeyDown={sidebarResize.onKeyDown}
          />
        )}
      </div>

      {/* Keep navigation outside the clipped/composited chat content. */}
      <div className={cx('areqa-chat-sidebar-floating-action', styles.sidebarFloatingAction)}>
        <button
          className={cx(
            'areqa-chat-sidebar-toggle',
            styles.iconActionButton,
            styles.sidebarActionButton,
          )}
          onClick={toggleSidebar}
          aria-label={t(sidebarOpen ? 'closeSidebar' : 'openSidebar')}
          aria-expanded={sidebarOpen}
          aria-controls={sidebarId}
          data-desktop-collapsed={desktopCollapsed}
          data-mobile-open={mobileOpen}
          type="button"
        >
          <PanelLeftOpen size={20} data-sidebar-icon="open" aria-hidden="true" />
          <PanelLeftClose size={20} data-sidebar-icon="close" aria-hidden="true" />
        </button>
      </div>

      {/* Main Content */}
      <div className={cx('areqa-chat-main', styles.main)}>
        <LongConversationReminder
          userId={historyUserId}
          conversationId={activeConversationId}
          replyCount={messages.filter((message) => message.role === 'assistant' && !message.isStreaming).length}
          blocked={!isChatReady || isStreaming || isGeneratingImage || isMessageHandoffLoading || isLiveTutorOpen}
          onNewConversation={handleNewConversation}
        />

        {/* Error Banner */}
        {error && (
          <div className={styles.errorBanner}>
            <AlertCircle size={16} />
            <span>{error.message}</span>
            <X
              size={16}
              className={styles.errorDismiss}
              onClick={dismissError}
            />
          </div>
        )}

        {/* Content Area */}
        <div
          className={cx(
            'areqa-chat-content',
            shouldShowEmptyChat && !isLiveTutorOpen && !gumPanelType && 'areqa-chat-content-empty',
            isLiveTutorOpen && !gumPanelType && 'areqa-chat-content-live-tutor',
            useAvatarSplitLayout && 'areqa-chat-content-avatar-split',
            styles.content,
            shouldShowEmptyChat && !isLiveTutorOpen && !gumPanelType && styles.contentEmpty,
            isLiveTutorOpen && !gumPanelType && styles.contentLiveTutor,
            useAvatarSplitLayout && styles.contentAvatarSplit,
          )}
          style={useAvatarSplitLayout
            ? ({ '--areqa-avatar-pane-width': `${avatarPaneWidth}px` } as React.CSSProperties)
            : undefined}
        >
          {mailboxEnabled && gumPanelType === 'mailbox' ? (
            <MailboxPanel onClose={() => setGumPanelType(null)} />
          ) : gumPanelType === 'notes' ? (
            <NotesPanel onClose={() => setGumPanelType(null)} />
          ) : gumPanelType === 'memory' ? (
            <GumPanel
              open={true}
              type={gumPanelType}
              onClose={() => setGumPanelType(null)}
            />
          ) : (
            <div className={cx(styles.liveTutorWorkspace, useAvatarSplitLayout && styles.liveTutorWorkspaceSplit)}>
              <div className={cx('areqa-chat-response-pane', styles.responsePane, useAvatarSplitLayout && styles.responsePaneSplit)}>
                <div className={cx('areqa-chat-floating-actions', styles.floatingActions)}>
                  {!gumPanelType && !isEmpty && (
                    <>
                      <button
                        className={cx(styles.shareButton)}
                        disabled={isSharing}
                        onClick={handleShareConversation}
                        type="button"
                      >
                        <Share2 size={16} aria-hidden="true" />
                        <span>{t('shareConversation')}</span>
                      </button>
                      <Dropdown
                        menu={{
                          items: [
                            { key: 'md', label: t('exportMarkdown'), icon: <FileCode size={16} /> },
                            { key: 'pdf', label: t('exportPdf'), icon: <FileImage size={16} /> },
                            { key: 'docx', label: t('exportDocx'), icon: <FileText size={16} /> },
                          ],
                          onClick: async (info) => {
                            try {
                              if (info.key === 'md') {
                                exportToMarkdown(messages);
                              } else if (info.key === 'pdf') {
                                const hide = antMessageApi.loading(t('exportPdfLoading'), 0);
                                await exportToPdf();
                                hide();
                              } else if (info.key === 'docx') {
                                const hide = antMessageApi.loading(t('exportDocxLoading'), 0);
                                await exportToDocx(messages);
                                hide();
                              }
                              antMessageApi.success(t('exportSuccess'));
                            } catch (err) {
                              antMessageApi.error(t('exportFailed'));
                              console.error('Export failed:', err);
                            }
                          }
                        }}
                        trigger={['click']}
                        placement="bottomLeft"
                      >
                        <button
                          className={cx(styles.iconActionButton)}
                          aria-label={t('shareConversationMenu')}
                          type="button"
                        >
                          <MoreHorizontal size={20} />
                        </button>
                      </Dropdown>
                    </>
                  )}
                </div>

                {/* Message List */}
                <div
                  id="export-chat-container"
                  className={cx(
                    'areqa-chat-message-area',
                    isLiveTutorOpen && 'areqa-chat-message-area-live-tutor',
                    styles.messageArea,
                    isLiveTutorOpen && styles.messageAreaLiveTutor,
                    hideLiveTutorMessages && !isGeneratingImage && styles.messageAreaLiveTutorEmpty,
                  )}
                >
                  {activeImageRequest && !activeImageRequest.assistantMessageId ? (
                    <ImageGenerationLoading caption={language === 'en' ? 'Preparing image…' : language === 'zh-CN' ? '正在准备图片…' : '正在準備圖片…'} />
                  ) : !isEmptyLiveTutor && (
                    <MessageList
                      liveVoice={isLiveTutorOpen}
                      onRegenerate={handleRegenerate}
                      onEdit={handleEdit}
                      onDeleteLatestTurn={handleDeleteLatestTurn}
                      onAddNote={handleAddNote}
                      onSelectSuggestion={handleSend}
                    />
                  )}
                </div>

                {!useAvatarSplitLayout && (
                  <LiveTutorPanel activeConversationId={activeConversationId} hasMessages={!isEmpty} />
                )}

                {/* Chat Input */}
                <div className={cx('areqa-chat-input-area', styles.inputArea)}>
                  <ChatInput
                    key={activeConversationId ?? 'new'}
                    onSend={handleSend}
                    disabled={(isStreaming && !isLiveTutorOpen) || isGeneratingImage}
                    placeholder={
                      isStreaming
                        ? t('thinkingPlaceholder')
                        : t('askPlaceholder')
                    }
                    isStreaming={isStreaming}
                    isGeneratingImage={isGeneratingImage}
                    onStop={handleStop}
                    onOpenLiveTutor={openLiveTutor}
                    isLiveVoiceActive={isLiveTutorOpen}
                    isLiveVoiceMuted={isLiveTutorMuted}
                    isLiveVoiceAvatarEnabled={isLiveTutorAvatarEnabled}
                    onToggleLiveVoiceMute={toggleLiveTutorMute}
                    onToggleLiveVoiceAvatar={toggleLiveTutorAvatar}
                    onCloseLiveVoice={requestCloseLiveTutor}
                  />
                </div>
              </div>

              {useAvatarSplitLayout && (
                <>
                  <div
                    className={styles.avatarResizeHandle}
                    role="separator"
                    aria-orientation="vertical"
                    aria-label="Resize avatar panel"
                    aria-valuemin={AVATAR_PANE_MIN_WIDTH}
                    aria-valuemax={AVATAR_PANE_MAX_WIDTH}
                    aria-valuenow={Math.round(avatarPaneWidth)}
                    tabIndex={0}
                    onPointerDown={startAvatarPaneResize}
                    onKeyDown={handleAvatarResizeKeyDown}
                  />
                  <aside className={styles.avatarPane} aria-label="Live Tutor avatar">
                    <LiveTutorPanel
                      activeConversationId={activeConversationId}
                      hasMessages={!isEmpty}
                      layout="side-pane"
                    />
                  </aside>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Text Selection Toolbar */}
      <TextSelectionToolbar />

      {/* Proactive Polling & Telemetry */}
      {(mailboxEnabled || compeerEnabled) && <ProactiveManager />}

      <AuthPrompt open={showAuthPrompt && !user} onDismiss={dismissAuthPrompt} />
    </div>
  );
}

export default ChatContainer;
