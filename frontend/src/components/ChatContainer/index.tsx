'use client';

/**
 * ChatContainer Component
 * Main container that assembles the complete chat interface
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Menu, X, AlertCircle, MoreHorizontal, FileText, FileImage, FileCode, Share2 } from 'lucide-react';
import { App, Dropdown } from 'antd';
import { exportToMarkdown, exportToDocx, exportToPdf } from '@/utils/exportChat';
import { useChatStore, chatSelectors } from '@/store/chat';
import { useConversationStore, conversationSelectors } from '@/store/conversation';
import { sendMessage, initializeChatService, cancelCurrentStream, regenerateMessage, editUserMessage } from '@/services/chat';
import { ConversationList } from '@/components/ConversationList';
import { MessageList } from '@/components/MessageList';
import { ChatInput } from '@/components/ChatInput';
import { TextSelectionToolbar } from '@/components/TextSelectionToolbar';
import { GumPanel } from '@/components/GumPanel';
import { MailboxPanel } from '@/components/MailboxPanel';
import { ProactiveManager } from '@/components/ProactiveManager';
import { AuthPrompt } from '@/components/Auth';
import { supabase } from '@/lib/supabase';
import { initializeAuth, useAuthStore } from '@/store/auth';
import { useFeatureStore } from '@/store/features';
import { syncService } from '@/services/syncService';
import { databaseService } from '@/services/database';
import { getAuthToken } from '@/database/db';
import { useStyles } from './styles';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';

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


/**
 * ChatContainer is the main component that assembles the chat interface
 */
export function ChatContainer({ className }: ChatContainerProps) {
  const { styles, cx } = useStyles();
  const { message: antMessageApi } = App.useApp();
  const { t } = useUserPreferences();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [gumPanelType, setGumPanelType] = useState<SidePanelType>(null);
  const [showAuthPrompt, setShowAuthPrompt] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [isChatReady, setIsChatReady] = useState(false);
  const mailboxEnabled = useFeatureStore((state) => state.mailbox);
  const compeerEnabled = useFeatureStore((state) => state.compeer);
  const fetchFeatures = useFeatureStore((state) => state.fetchFeatures);
  const user = useAuthStore((state) => state.user);
  const isAuthInitialized = useAuthStore((state) => state.isInitialized);
  const validateSession = useAuthStore((state) => state.validateSession);

  // Get state from stores
  const isStreaming = useChatStore((state) => state.isStreaming);
  const error = useChatStore((state) => state.error);
  const setError = useChatStore((state) => state.setError);
  const messages = useChatStore(chatSelectors.displayMessages);
  const isEmpty = messages.length === 0;

  const activeConversation = useConversationStore((state) =>
    conversationSelectors.activeConversation(state)
  );
  const activeConversationId = useConversationStore(
    (state) => state.activeConversationId
  );
  const landingPromptSent = useRef(false);

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

    const stabilizeViewport = () => {
      updateViewportHeight();
      window.setTimeout(() => {
        window.scrollTo(0, 0);
        updateViewportHeight();
      }, 0);
    };

    updateViewportHeight();
    viewport?.addEventListener('resize', updateViewportHeight);
    viewport?.addEventListener('scroll', updateViewportHeight);
    window.addEventListener('resize', updateViewportHeight);
    window.addEventListener('orientationchange', updateViewportHeight);
    window.addEventListener('focus', stabilizeViewport);
    window.addEventListener('pageshow', stabilizeViewport);
    document.addEventListener('visibilitychange', stabilizeViewport);

    return () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }
      viewport?.removeEventListener('resize', updateViewportHeight);
      viewport?.removeEventListener('scroll', updateViewportHeight);
      window.removeEventListener('resize', updateViewportHeight);
      window.removeEventListener('orientationchange', updateViewportHeight);
      window.removeEventListener('focus', stabilizeViewport);
      window.removeEventListener('pageshow', stabilizeViewport);
      document.removeEventListener('visibilitychange', stabilizeViewport);
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

    const loadAuthenticatedHistory = async () => {
      if (!user) {
        useConversationStore.getState().clearState();
        useChatStore.getState().clearMessages();
        useChatStore.getState().resetStreamingState();
        if (typeof indexedDB !== 'undefined') {
          try {
            await databaseService.conversation.clearGuestData();
          } catch (error) {
            console.error('Failed to clear legacy guest history:', error);
          }
        }
        if (!cancelled) setIsChatReady(true);
        return;
      }

      try {
        if (user) setShowAuthPrompt(false);
        await syncService.pullFromCloud(user.id);
        if (!cancelled) await initializeChatService(user.id);
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
  }, [isAuthInitialized, user]);

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
    async function retryableSend(content: string, attachments: File[] = []) {
      try {
        const result = await sendMessage(content, activeConversationId || undefined, attachments);
        if (result?.completed) {
          const { data: { session } } = await supabase.auth.getSession();
          if (!session) setShowAuthPrompt(true);
        }
        return result;
      } catch (err) {
        console.error('Failed to send message:', err);

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
                    void retryableSend(content, attachments).catch(() => undefined); // Retry with the same request
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
    [activeConversationId, antMessageApi, t]
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
    setSidebarOpen(false);
    setGumPanelType(null); // Return to chat view
  }, []);

  // Handle new conversation
  const handleNewConversation = useCallback(() => {
    // Just clear UI state and deselect active conversation
    useConversationStore.getState().clearActiveConversation();
    useChatStore.getState().clearMessages();
    useChatStore.getState().resetStreamingState();
    setSidebarOpen(false);
    setGumPanelType(null); // Return to chat view
  }, []);

  // Toggle sidebar
  const toggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  // Close sidebar
  const closeSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  // Dismiss error
  const dismissError = useCallback(() => {
    setError(null);
  }, [setError]);

  const dismissAuthPrompt = useCallback(() => {
    setShowAuthPrompt(false);
  }, []);

  // Handle stop streaming
  const handleStop = useCallback(async () => {
    await cancelCurrentStream();
  }, []);

  // Handle regenerate message
  const handleRegenerate = useCallback(async (messageId: string) => {
    try {
      await regenerateMessage(messageId);
    } catch (err) {
      console.error('Failed to regenerate message:', err);
      antMessageApi.error('重新生成失敗，請稍後再試');
    }
  }, [antMessageApi]);

  // Handle edit user message
  const handleEdit = useCallback(async (messageId: string, newContent: string) => {
    try {
      await editUserMessage(messageId, newContent);
    } catch (err) {
      console.error('Failed to edit message:', err);
      antMessageApi.error('編輯訊息失敗，請稍後再試');
    }
  }, [antMessageApi]);

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

    const token = getAuthToken();
    if (!token) {
      antMessageApi.warning(t('shareLoginRequired'));
      setShowAuthPrompt(true);
      return;
    }

    setIsSharing(true);
    try {
      const response = await fetch(`/api/share/conversations/${activeConversation.id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          conversation: activeConversation,
          messages,
        }),
      });

      const payload = await response.json().catch(() => null) as { token?: string } | null;
      if (!response.ok || !payload?.token) {
        throw new Error('Share API did not return a token');
      }

      const shareUrl = `${window.location.origin}/share/${payload.token}`;
      await navigator.clipboard.writeText(shareUrl);
      antMessageApi.success(t('shareLinkCopied'));
    } catch (error) {
      console.error('Failed to share conversation:', error);
      antMessageApi.error(t('shareLinkFailed'));
    } finally {
      setIsSharing(false);
    }
  }, [activeConversation, antMessageApi, messages, t, user]);

  return (
    <div className={cx('areqa-chat-shell', styles.container, className)}>
      {/* Sidebar Overlay (mobile) */}
      {sidebarOpen && (
        <div className={styles.sidebarOverlay} onClick={closeSidebar} />
      )}

      {/* Sidebar */}
      <div className={cx('areqa-chat-sidebar', styles.sidebar, sidebarOpen && styles.sidebarOpen)}>
        <ConversationList
          onSelect={handleConversationSelect}
          onNew={handleNewConversation}
          onToggleSidebar={toggleSidebar}
          onSelectGumPanel={(type) => {
            setGumPanelType(type);
            setSidebarOpen(false); // Close sidebar on mobile when opening panel
          }}
        />
      </div>

      {/* Main Content */}
      <div className={cx('areqa-chat-main', styles.main)}>
        {!gumPanelType && !isEmpty && (
          <div className={cx('areqa-chat-floating-actions', styles.floatingActions)}>
            <button
              className={cx(styles.iconActionButton, styles.sidebarActionButton, sidebarOpen && styles.sidebarActionButtonVisible)}
              onClick={toggleSidebar}
              aria-label={t('openSidebar')}
              type="button"
            >
              <Menu size={20} />
            </button>
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
          </div>
        )}

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
            isEmpty && !gumPanelType && 'areqa-chat-content-empty',
            styles.content,
            isEmpty && !gumPanelType && styles.contentEmpty,
          )}
        >
          {mailboxEnabled && gumPanelType === 'mailbox' ? (
            <MailboxPanel onClose={() => setGumPanelType(null)} />
          ) : gumPanelType === 'memory' ? (
            <GumPanel
              open={true}
              type={gumPanelType}
              onClose={() => setGumPanelType(null)}
            />
          ) : (
            <>
              {/* Message List */}
              <div id="export-chat-container" className={cx('areqa-chat-message-area', styles.messageArea)}>
                <MessageList 
                  onRegenerate={handleRegenerate} 
                  onEdit={handleEdit} 
                  onSelectSuggestion={handleSend}
                />
              </div>

              {/* Chat Input */}
              <div className={cx('areqa-chat-input-area', styles.inputArea)}>
                <ChatInput
                  key={activeConversationId ?? 'new'}
                  onSend={handleSend}
                  disabled={isStreaming}
                  placeholder={
                    isStreaming
                      ? t('thinkingPlaceholder')
                      : t('askPlaceholder')
                  }
                  isStreaming={isStreaming}
                  onStop={handleStop}
                />
              </div>
            </>
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
