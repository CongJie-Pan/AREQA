'use client';

/**
 * ChatInput Component
 * Text input for sending messages with validation
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Send, Square, Database, X, CornerDownRight, Plus, FileText, Image as ImageIcon } from 'lucide-react';
import { message, Tooltip } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { useChatStore } from '@/store/chat';
import { useStyles } from './styles';
import { normalizeDisplayMathBlocks, rehypeMathSource } from '@/utils/markdownMath';

/** Maximum allowed message length */
const MAX_MESSAGE_LENGTH = 4000;
/** Warning threshold for character count */
const WARNING_THRESHOLD = 0.9;
const MAX_ATTACHMENT_COUNT = 5;
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const SUPPORTED_ATTACHMENT_TYPES = new Set([
  'image/png', 'image/jpeg', 'image/webp', 'image/gif',
  'application/pdf', 'text/plain', 'text/markdown',
]);

export interface ChatInputProps {
  /** Callback when message is sent */
  onSend: (message: string, attachments?: File[]) => void | Promise<void>;
  /** Whether input is disabled */
  disabled?: boolean;
  /** Placeholder text */
  placeholder?: string;
  /** Class name for styling */
  className?: string;
  /** Maximum message length (default: 4000) */
  maxLength?: number;
  /** Whether AI is currently streaming response */
  isStreaming?: boolean;
  /** Callback when stop button is clicked */
  onStop?: () => void;
}

/**
 * ChatInput provides text input for sending messages
 * Supports Enter to send, Shift+Enter for new line
 */
export function ChatInput({
  onSend,
  disabled = false,
  placeholder = '問我任何問題...',
  className,
  maxLength = MAX_MESSAGE_LENGTH,
  isStreaming = false,
  onStop,
}: ChatInputProps) {
  const { styles, cx } = useStyles();
  const [value, setValue] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Connect to global state for mode togglers
  const useRag = useChatStore((state) => state.useRag);
  const quotedText = useChatStore((state) => state.quotedText);
  const toggleRag = useChatStore((state) => state.toggleRag);
  const setQuotedText = useChatStore((state) => state.setQuotedText);

  // Calculate character count and warning state
  const charCount = value.length;
  const isNearLimit = charCount > maxLength * WARNING_THRESHOLD;
  const isOverLimit = charCount > maxLength;
  const hasMath = /(?:\$\$?[\s\S]+?\$\$?|\\\(|\\\[)/.test(value);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [value]);

  // Focus textarea when quotedText changes
  useEffect(() => {
    if (quotedText && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [quotedText]);

  // Focus textarea on mount
  useEffect(() => {
    if (textareaRef.current && !disabled) {
      textareaRef.current.focus();
    }
  }, [disabled]);

  const handleSend = useCallback(() => {
    const trimmedValue = value.trim();

    // Validation checks
    if (!trimmedValue && !quotedText && attachments.length === 0) {
      return;
    }

    if (disabled) return;

    // Check message length
    if (trimmedValue.length > maxLength) {
      message.error(`訊息過長。上限為 ${maxLength} 個字元。`);
      return;
    }

    // Construct final message with quote if exists
    let finalMessage = trimmedValue;
    if (quotedText) {
      const formattedQuote = quotedText
        .split('\n')
        .map(line => (line.startsWith('>') ? line : `> ${line}`))
        .join('\n');
      finalMessage = `${formattedQuote}\n\n${trimmedValue}`;
    }

    if (attachments.length > 0) {
      onSend(finalMessage, attachments);
    } else {
      onSend(finalMessage);
    }
    setValue('');
    setAttachments([]);
    setQuotedText(null); // Clear quote after sending

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, attachments, disabled, onSend, maxLength, quotedText, setQuotedText]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Ignore if user is composing text (e.g. using IME for Chinese)
      if (e.nativeEvent.isComposing) return;

      // Enter to send, Shift+Enter for new line
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setValue(e.target.value);
    },
    []
  );

  const handleAttachmentChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (selected.length === 0) return;

    const candidates = [...attachments, ...selected];
    if (candidates.length > MAX_ATTACHMENT_COUNT) {
      message.error(`每次最多可附加 ${MAX_ATTACHMENT_COUNT} 個檔案。`);
      return;
    }

    let totalSize = 0;
    for (const attachment of candidates) {
      if (!SUPPORTED_ATTACHMENT_TYPES.has(attachment.type)) {
        message.error('僅支援 PNG、JPEG、WEBP、GIF、PDF、TXT 與 Markdown 檔案。');
        return;
      }
      if (attachment.size === 0) {
        message.error('不接受空白附件。');
        return;
      }
      if (attachment.size > MAX_ATTACHMENT_BYTES) {
        message.error('單一附件不得超過 5 MB。');
        return;
      }
      totalSize += attachment.size;
    }
    if (totalSize > MAX_TOTAL_ATTACHMENT_BYTES) {
      message.error('附件總大小不得超過 20 MB。');
      return;
    }

    setAttachments(candidates);
  }, [attachments]);

  const removeAttachment = useCallback((target: File) => {
    setAttachments((current) => current.filter((attachment) => attachment !== target));
  }, []);

  const canSend = (value.trim().length > 0 || attachments.length > 0) && !disabled && !isOverLimit;

  return (
    <div className={cx(styles.container, className)}>
      {/* Quote Preview */}
      {quotedText && (
        <div className={styles.quotePreview}>
          <CornerDownRight size={14} className={styles.quoteArrow} />
          <div className={styles.quoteContent}>{quotedText}</div>
          <button
            className={styles.quoteClose}
            onClick={() => setQuotedText(null)}
            aria-label="取消引用"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        className={styles.textarea}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        maxLength={maxLength + 100}
        aria-label="訊息輸入框"
        aria-describedby="char-count"
      />

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,text/plain,text/markdown,.txt,.md"
        multiple
        hidden
        onChange={handleAttachmentChange}
        aria-label="選擇附件"
      />

      {attachments.length > 0 && (
        <div className={styles.attachmentList} aria-label="待送附件">
          {attachments.map((attachment) => (
            <div className={styles.attachmentChip} key={`${attachment.name}-${attachment.lastModified}`}>
              {attachment.type.startsWith('image/') ? <ImageIcon size={14} /> : <FileText size={14} />}
              <span>{attachment.name}</span>
              <button type="button" onClick={() => removeAttachment(attachment)} aria-label={`移除附件 ${attachment.name}`}>
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      {hasMath && (
        <div className={styles.mathPreview} aria-label="LaTeX 預覽">
          <div className={styles.mathPreviewLabel}>公式預覽</div>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }], rehypeMathSource]}
          >
            {normalizeDisplayMathBlocks(value)}
          </ReactMarkdown>
        </div>
      )}

      {/* Bottom toolbar: mode buttons left, send button right */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <Tooltip title="加入圖片或文件" color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button
              type="button"
              className={styles.attachmentButton}
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              aria-label="加入附件"
            >
              <Plus size={18} />
            </button>
          </Tooltip>

          <div style={{ display: 'none' }}>
            <Tooltip title="切換 RAG 模式" color="#262626" styles={{ container: { color: '#ffffff' } }}>
              <button
                type="button"
                className={cx(styles.toggleButton, useRag && styles.toggleButtonActive)}
                onClick={toggleRag}
                aria-label="切換 RAG 模式"
              >
                <Database size={15} />
                <span>RAG模式</span>
              </button>
            </Tooltip>
          </div>

          <span
            id="char-count"
            className={styles.charCount}
            style={{
              color: isOverLimit ? '#ff4d4f' : isNearLimit ? '#faad14' : undefined,
            }}
          >
            {charCount}/{maxLength}
          </span>
        </div>

        <div className={styles.toolbarRight}>
          {isStreaming && onStop ? (
            <button
              type="button"
              className={cx(styles.sendButton, styles.stopButton)}
              onClick={onStop}
              aria-label="停止生成"
            >
              <Square size={16} fill="currentColor" />
            </button>
          ) : (
            <button
              type="button"
              className={styles.sendButton}
              onClick={handleSend}
              disabled={!canSend}
              aria-label="發送訊息"
            >
              <Send size={18} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default ChatInput;
