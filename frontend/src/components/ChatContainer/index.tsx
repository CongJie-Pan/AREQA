'use client';

/**
 * ChatContainer Component
 * Main container that assembles the complete chat interface
 */

import React, { useState, useCallback, useEffect } from 'react';
import { Menu, X, AlertCircle } from 'lucide-react';
import { App } from 'antd';
import { useChatStore, chatSelectors } from '@/store/chat';
import { useConversationStore, conversationSelectors } from '@/store/conversation';
import { sendMessage, initializeChatService, cancelCurrentStream, regenerateMessage, editUserMessage } from '@/services/chat';
import { ConversationList } from '@/components/ConversationList';
import { MessageList } from '@/components/MessageList';
import { ChatInput } from '@/components/ChatInput';
import { TextSelectionToolbar } from '@/components/TextSelectionToolbar';
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

/**
 * ChatContainer is the main component that assembles the chat interface
 */
export function ChatContainer({ className }: ChatContainerProps) {
  const { styles, cx } = useStyles();
  const { message: antMessageApi } = App.useApp();
  const [sidebarOpen, setSidebarOpen] = useState(false);

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

  // Initialize on mount
  useEffect(() => {
    initializeChatService();
  }, []);

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
    async function retryableSend(content: string) {
      try {
        await sendMessage(content, activeConversationId || undefined);
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
                    retryableSend(content); // Retry with same content
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
      }
    },
    [activeConversationId, antMessageApi]
  );

  // Handle conversation selection
  const handleConversationSelect = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  // Handle new conversation
  const handleNewConversation = useCallback(() => {
    // Just clear UI state and deselect active conversation
    useConversationStore.getState().clearActiveConversation();
    useChatStore.getState().clearMessages();
    useChatStore.getState().resetStreamingState();
    setSidebarOpen(false);
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
              {activeConversation?.title || ''}
            </h1>
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
        <div className={cx(styles.content, isEmpty && styles.contentEmpty)}>
          {/* Message List */}
          <div className={styles.messageArea}>
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
          </div>
        </div>
      </div>

      {/* Text Selection Toolbar */}
      <TextSelectionToolbar />
    </div>
  );
}

export default ChatContainer;
