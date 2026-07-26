'use client';

/**
 * ChatContainer Component
 * Main container that assembles the complete chat interface
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Menu, X, AlertCircle, MoreVertical, FileText, FileImage, FileCode } from 'lucide-react';
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
import { syncService } from '@/services/syncService';
import { databaseService } from '@/services/database';
import { useStyles } from './styles';

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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [gumPanelType, setGumPanelType] = useState<SidePanelType>(null);
  const [showAuthPrompt, setShowAuthPrompt] = useState(false);
  const [isChatReady, setIsChatReady] = useState(false);
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
    const viewport = window.visualViewport;
    const root = document.documentElement;
    let animationFrameId: number | null = null;

    const updateViewportHeight = () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }

      animationFrameId = window.requestAnimationFrame(() => {
        const viewportHeight = viewport?.height ?? window.innerHeight;
        root.style.setProperty(
          '--areqa-visual-viewport-height',
          `${Math.round(viewportHeight)}px`,
        );
        animationFrameId = null;
      });
    };

    updateViewportHeight();
    viewport?.addEventListener('resize', updateViewportHeight);
    viewport?.addEventListener('scroll', updateViewportHeight);
    window.addEventListener('resize', updateViewportHeight);
    window.addEventListener('orientationchange', updateViewportHeight);

    return () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }
      viewport?.removeEventListener('resize', updateViewportHeight);
      viewport?.removeEventListener('scroll', updateViewportHeight);
      window.removeEventListener('resize', updateViewportHeight);
      window.removeEventListener('orientationchange', updateViewportHeight);
      root.style.removeProperty('--areqa-visual-viewport-height');
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
                  重試
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
    [activeConversationId, antMessageApi]
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

  return (
    <div className={cx(styles.container, className)}>
      {/* Sidebar Overlay (mobile) */}
      {sidebarOpen && (
        <div className={styles.sidebarOverlay} onClick={closeSidebar} />
      )}

      {/* Sidebar */}
      <div className={cx(styles.sidebar, sidebarOpen && styles.sidebarOpen)}>
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
      <div className={styles.main}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <button
              className={cx(styles.menuButton, sidebarOpen && styles.menuButtonVisible)}
              onClick={toggleSidebar}
              aria-label="打開選單"
            >
              <Menu size={20} />
            </button>
            <h1 className={styles.headerTitle}>
              {gumPanelType ? '' : (activeConversation?.title || '')}
            </h1>
          </div>
          
          <div className={styles.headerRight}>
            {!gumPanelType && !isEmpty && (
              <Dropdown
                menu={{
                  items: [
                    { key: 'md', label: '下載為 Markdown (.md)', icon: <FileCode size={16} color="white" /> },
                    { key: 'pdf', label: '下載為 PDF (.pdf)', icon: <FileImage size={16} color="white" /> },
                    { key: 'docx', label: '下載為 Word (.docx)', icon: <FileText size={16} color="white" /> },
                  ],
                  onClick: async (info) => {
                    try {
                      if (info.key === 'md') {
                        exportToMarkdown(messages);
                      } else if (info.key === 'pdf') {
                        const hide = antMessageApi.loading('正在產生 PDF，請稍候...', 0);
                        await exportToPdf();
                        hide();
                      } else if (info.key === 'docx') {
                        const hide = antMessageApi.loading('正在產生 Word 文件，請稍候...', 0);
                        await exportToDocx(messages);
                        hide();
                      }
                      antMessageApi.success('下載成功！');
                    } catch (err) {
                      antMessageApi.error('下載失敗，請稍後再試');
                      console.error('Export failed:', err);
                    }
                  }
                }}
                trigger={['click']}
                placement="bottomRight"
              >
                <button
                  className={styles.menuButton}
                  style={{ display: 'flex', opacity: 1, pointerEvents: 'auto', visibility: 'visible', color: 'rgba(255, 255, 255, 0.65)' }}
                  aria-label="匯出對話"
                >
                  <MoreVertical size={20} />
                </button>
              </Dropdown>
            )}
          </div>
        </div>

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
        <div className={cx(styles.content, isEmpty && !gumPanelType && styles.contentEmpty)}>
          {gumPanelType === 'mailbox' ? (
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
              <div id="export-chat-container" className={styles.messageArea}>
                <MessageList 
                  onRegenerate={handleRegenerate} 
                  onEdit={handleEdit} 
                  onSelectSuggestion={handleSend}
                />
              </div>

              {/* Chat Input */}
              <div className={styles.inputArea}>
                <ChatInput
                  key={activeConversationId ?? 'new'}
                  onSend={handleSend}
                  disabled={isStreaming}
                  placeholder={
                    isStreaming
                      ? '正在努力思考...'
                      : '歡迎問我問題...'
                  }
                  isStreaming={isStreaming}
                  onStop={handleStop}
                />
                {isEmpty && (
                  <div style={{
                    fontFamily: 'ChenYuluoyan, sans-serif',
                    fontWeight: 'normal',
                    fontSize: '22px',
                    textAlign: 'center',
                    color: '#fff',
                    marginTop: '20px',
                    letterSpacing: '3px'
                  }}>
                    懂你所學，伴你所讀
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Text Selection Toolbar */}
      <TextSelectionToolbar />

      {/* Proactive Polling & Telemetry */}
      <ProactiveManager />

      <AuthPrompt open={showAuthPrompt && !user} onDismiss={dismissAuthPrompt} />
    </div>
  );
}

export default ChatContainer;
