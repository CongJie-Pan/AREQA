'use client';

/**
 * MessageItem Component
 * Displays a single message in the conversation
 */

import React, { memo, useCallback, useState } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, RefreshCw, Edit, CornerDownRight } from 'lucide-react';
import { Tooltip, App } from 'antd';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { SuggestedQuestions } from '@/components/SuggestedQuestions';
import { Citations } from '@/components/Citations';
import { RAGStatusPanel } from '@/components/RAGStatusPanel';
import type { CitationSource } from '@/components/Citations';
import type { DisplayMessage } from '@/store/chat';
import { useStyles } from './styles';

/**
 * Safe URL protocols whitelist
 */
const SAFE_URL_PROTOCOLS = ['http:', 'https:', 'mailto:'];

/**
 * Validate URL is safe (http/https/mailto only)
 */
function isSafeUrl(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const urlObj = new URL(url);
    return SAFE_URL_PROTOCOLS.includes(urlObj.protocol);
  } catch {
    // Relative URLs are safe
    return url.startsWith('/') || url.startsWith('#');
  }
}

/**
 * Custom ReactMarkdown components for XSS protection and custom styling
 */
type Styles = Record<string, string>;
type Cx = (...classNames: Array<string | false | null | undefined>) => string;
type WindowWithFind = Window & {
  find?: (
    searchString: string,
    caseSensitive?: boolean,
    backwards?: boolean,
    wrapAround?: boolean,
    wholeWord?: boolean,
    searchInFrames?: boolean,
    showDialog?: boolean
  ) => boolean;
};

const createMarkdownComponents = (
  styles: Styles,
  cx: Cx,
  onQuoteClick: (text: string) => void
): Components => ({
  // Custom blockquote for citations
  blockquote: ({ children }) => {
    // Extract text content from children to find it in the DOM
    const extractText = (node: React.ReactNode): string => {
      if (typeof node === 'string') return node;
      if (Array.isArray(node)) return node.map(extractText).join('');
      if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
        return extractText(node.props.children);
      }
      return '';
    };
    const textContent = extractText(children).trim();

    return (
      <blockquote 
        className={cx(styles.quoteBlock, 'interactive-quote')} 
        onClick={() => onQuoteClick(textContent)}
        style={{ cursor: 'pointer' }}
        title="點擊以在文中反白此段落"
      >
        <CornerDownRight size={14} className={styles.quoteBlockArrow} />
        <div className={styles.quoteBlockContent}>
          {children}
        </div>
      </blockquote>
    );
  },
  // Sanitize links - only allow safe protocols
  a: ({ href, children, ...props }) => {
    if (!isSafeUrl(href)) {
      return <span>{children}</span>;
    }
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        {...props}
      >
        {children}
      </a>
    );
  },
  // Sanitize images - only allow safe src URLs
  img: ({ src, alt, ...props }) => {
    const isValidSrc = src && typeof src === 'string' && (
      src.startsWith('http://') ||
      src.startsWith('https://') ||
      src.startsWith('data:image/')
    );
    if (!isValidSrc) return null;
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src as string} alt={alt || ''} {...props} />;
  },
  // Prevent script tags (should be blocked by default, but extra safety)
  script: () => null,
});

export interface MessageItemProps {
  /** Message data */
  message: DisplayMessage;
  /** Whether this message is currently streaming */
  isStreaming?: boolean;
  /** Current thinking state for streaming messages */
  thinking?: {
    content: string;
    isThinking: boolean;
    duration?: number;
  };
  /** RAG status metadata */
  ragInfo?: {
    status: 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done';
    message: string;
    sources: CitationSource[];
  };
  /** Callback when regenerate button is clicked (AI messages only) */
  onRegenerate?: (messageId: string) => void;
  /** Callback when edit is submitted (user messages only) */
  onEdit?: (messageId: string, newContent: string) => void;
  /** Whether this is the last message in the list (to show suggested questions) */
  isLast?: boolean;
  /** Callback when a suggested question is clicked */
  onSelectSuggestion?: (question: string) => void;
  /** Optional class name for custom styling */
  className?: string;
}

/**
 * MessageItem displays a single chat message
 */
export const MessageItem = memo(function MessageItem({
  message,
  isStreaming = false,
  thinking,
  ragInfo,
  onRegenerate,
  onEdit,
  isLast = false,
  onSelectSuggestion,
  className,
}: MessageItemProps) {
  const { styles, cx } = useStyles();
  const { message: antMessageApi } = App.useApp();
  const isUser = message.role === 'user';
  const [bubbleEl, setBubbleEl] = useState<HTMLDivElement | null>(null);
  const setBubbleRef = useCallback((node: HTMLDivElement | null) => {
    setBubbleEl(node);
  }, []);

  // Handle clicking on a quote bubble to highlight text in the original message
  const handleQuoteClick = useCallback((quoteText: string) => {
    if (!bubbleEl || !quoteText) return;

    // Clear any existing selection first
    const selection = window.getSelection();
    if (selection) selection.removeAllRanges();

    // 1. First attempt: Use DOM TreeWalker (precise but sensitive to node splitting)
    const walk = document.createTreeWalker(bubbleEl, NodeFilter.SHOW_TEXT, null);
    let node: Node | null;
    let found = false;
    
    while ((node = walk.nextNode())) {
      const text = node.textContent || '';
      const index = text.indexOf(quoteText);
      
      if (index !== -1 && node.parentElement) {
        // Skip highlighting within quote blocks themselves
        if (node.parentElement.closest('.interactive-quote')) continue;

        node.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });

        try {
          const range = document.createRange();
          range.setStart(node, index);
          range.setEnd(node, index + quoteText.length);
          
          if (selection) {
            selection.addRange(range);
            found = true;
          }
        } catch (e) {
          console.warn('Range highlight failed, falling back:', e);
        }
        break;
      }
    }

    // 2. Second attempt: window.find (if supported and first attempt failed)
    // This is more robust for text split across multiple inline elements (like strong, em, code)
    const windowWithFind = window as WindowWithFind;
    if (!found && typeof windowWithFind.find === 'function') {
      // Note: window.find is non-standard but widely supported in browsers for this specific use case
      const res = windowWithFind.find(quoteText, false, false, true, false, true, false);
      if (res) found = true;
    }

    // 3. Clear selection after 6 seconds
    if (found) {
      setTimeout(() => {
        window.getSelection()?.removeAllRanges();
      }, 6000);
    }
  }, [bubbleEl]);

  const markdownComponents = React.useMemo(
    () => createMarkdownComponents(styles, cx, handleQuoteClick),
    [styles, cx, handleQuoteClick]
  );

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);

  // Handle copy message content
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      antMessageApi.success('已複製到剪貼簿');
    } catch {
      antMessageApi.error('複製失敗');
    }
  }, [message.content, antMessageApi]);

  // Handle regenerate
  const handleRegenerate = useCallback(() => {
    if (onRegenerate) {
      onRegenerate(message.id);
    }
  }, [onRegenerate, message.id]);

  // Handle entering edit mode
  const handleEditClick = useCallback(() => {
    setEditContent(message.content);
    setIsEditing(true);
  }, [message.content]);

  // Handle canceling edit
  const handleCancelEdit = useCallback(() => {
    setIsEditing(false);
    setEditContent(message.content);
  }, [message.content]);

  // Handle saving edit
  const handleSaveEdit = useCallback(() => {
    const trimmedContent = editContent.trim();
    if (trimmedContent && trimmedContent !== message.content && onEdit) {
      onEdit(message.id, trimmedContent);
    }
    setIsEditing(false);
  }, [editContent, message.content, message.id, onEdit]);

  // Handle keyboard shortcuts in edit mode
  const handleEditKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') {
      handleCancelEdit();
    } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleSaveEdit();
    }
  }, [handleCancelEdit, handleSaveEdit]);

  return (
    <div
      className={cx(styles.messageItem, isUser && styles.userMessage, className)}
      data-message-id={message.id}
    >
      {/* User Message: Simple bubble layout */}
      {isUser ? (
        <>
          {isEditing ? (
            /* Edit Mode */
            <div className={styles.editModeContainer}>
              <textarea
                className={styles.editTextarea}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                onKeyDown={handleEditKeyDown}
                autoFocus
                placeholder="輸入訊息..."
              />
              <div className={styles.editButtons}>
                <button
                  className={cx(styles.editButton, styles.editCancelButton)}
                  onClick={handleCancelEdit}
                >
                  取消
                </button>
                <button
                  className={cx(styles.editButton, styles.editSaveButton)}
                  onClick={handleSaveEdit}
                  disabled={!editContent.trim() || editContent.trim() === message.content}
                >
                  送出
                </button>
              </div>
            </div>
          ) : (
            /* Normal Display Mode */
            <div className={cx(styles.bubbleWrapper, 'bubbleWrapper')}>
              {(() => {
                // Split content into citation and the rest
                // Pattern matches one or more lines starting with '>' at the beginning
                const quoteMatch = message.content.match(/^((?:>[^\n]*(?:\n|$))+)\n*([\s\S]*)$/);
                
                if (quoteMatch && isUser) {
                  const rawCitation = quoteMatch[1];
                  const remainingText = quoteMatch[2].trim();
                  const cleanCitation = rawCitation.replace(/^>\s?/gm, '').trim();
                  
                  return (
                    <>
                      {/* 1. Citation: Outside bubble, transparent */}
                      <div 
                        className={cx(styles.quoteBlock, 'interactive-quote')}
                        onClick={() => handleQuoteClick(cleanCitation)}
                        style={{ cursor: 'pointer' }}
                      >
                        <CornerDownRight size={14} className={styles.quoteBlockArrow} />
                        <div className={styles.quoteBlockContent}>
                          {cleanCitation.split('\n').map((line, i) => (
                            <React.Fragment key={i}>
                              {line}
                              {i < cleanCitation.split('\n').length - 1 && <br />}
                            </React.Fragment>
                          ))}
                        </div>
                      </div>
                      
                      {/* 2. Main Query: Inside bubble */}
                      {remainingText && (
                        <div className={cx(styles.bubble, styles.userBubble)}>
                          <div className={styles.content}>
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={markdownComponents}
                              disallowedElements={['script', 'iframe', 'object', 'embed']}
                            >
                              {remainingText}
                            </ReactMarkdown>
                          </div>
                        </div>
                      )}
                    </>
                  );
                }

                // Default: render everything inside bubble
                return (
                  <div className={cx(styles.bubble, styles.userBubble)}>
                    <div className={styles.content}>
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={markdownComponents}
                        disallowedElements={['script', 'iframe', 'object', 'embed']}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                );
              })()}
              
              <div className={styles.userActionButtons}>
                <Tooltip title="複製訊息" color="#262626" styles={{ container: { color: '#ffffff' } }}>
                  <button
                    className={styles.actionButton}
                    onClick={handleCopy}
                    aria-label="複製訊息"
                  >
                    <Copy size={16} />
                  </button>
                </Tooltip>
                {onEdit && (
                  <Tooltip title="編輯訊息" color="#262626" styles={{ container: { color: '#ffffff' } }}>
                    <button
                      className={styles.actionButton}
                      onClick={handleEditClick}
                      aria-label="編輯訊息"
                    >
                      <Edit size={16} />
                    </button>
                  </Tooltip>
                )}
              </div>
            </div>
          )}
        </>
      ) : (
        /* AI Message: Bubble only */
        <div className={styles.assistantMessageWrapper}>
          {/* Bubble Wrapper */}
          <div className={cx(styles.bubbleWrapper, 'bubbleWrapper')}>
            {/* Message Bubble */}
            <div 
              ref={setBubbleRef}
              className={cx(styles.bubble, styles.assistantBubble)}
              data-role="assistant-bubble"
            >
              {/* RAG Status Panel - Should be at the top and only visible before thinking starts */}
              {ragInfo && ragInfo.status !== 'idle' && !thinking?.isThinking && !thinking?.content && !message.reasoning && (
                <RAGStatusPanel ragInfo={ragInfo} />
              )}

              {/* Thinking Panel */}
              {(thinking?.isThinking || message.reasoning) && (
                <div className={styles.thinkingPanelWrapper}>
                  <ThinkingPanel
                    content={thinking?.content || message.reasoning?.content}
                    duration={thinking?.duration || message.reasoning?.duration}
                    isThinking={thinking?.isThinking}
                    defaultExpanded={thinking?.isThinking}
                  />
                </div>
              )}

              {/* Message Content */}
              <div className={styles.content}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                  disallowedElements={['script', 'iframe', 'object', 'embed']}
                >
                  {message.content}
                </ReactMarkdown>
                {/* Streaming cursor */}
                {isStreaming && !thinking?.isThinking && (
                  <span className={styles.streamingCursor} />
                )}
              </div>

              {/* Citations / Sources Panel */}
              {((message.sources && message.sources.length > 0) || 
                (ragInfo?.sources && ragInfo.sources.length > 0) || 
                (message.citations && message.citations.length > 0)) && (
                <div className={styles.citationsWrapper}>
                  <Citations 
                    citations={message.citations || []} 
                    sources={message.sources || ragInfo?.sources}
                  />
                </div>
              )}

              {/* Suggested Questions - Only for last assistant message */}
              {isLast && !isUser && message.suggestions && message.suggestions.length > 0 && !isStreaming && (
                <SuggestedQuestions 
                  suggestions={message.suggestions} 
                  onSelect={(q) => onSelectSuggestion?.(q)}
                  disabled={isStreaming}
                />
              )}
            </div>

            {/* Action Buttons */}
            <div className={styles.actionButtons}>
              <Tooltip title="複製訊息" color="#262626" styles={{ container: { color: '#ffffff' } }}>
                <button
                  className={styles.actionButton}
                  onClick={handleCopy}
                  aria-label="複製訊息"
                >
                  <Copy size={16} />
                </button>
              </Tooltip>
              {onRegenerate && !isStreaming && (
                <Tooltip title="重新生成" color="#262626" styles={{ container: { color: '#ffffff' } }}>
                  <button
                    className={styles.actionButton}
                    onClick={handleRegenerate}
                    aria-label="重新生成訊息"
                  >
                    <RefreshCw size={16} />
                  </button>
                </Tooltip>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export default MessageItem;
