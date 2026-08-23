'use client';

/**
 * ChatInput Component
 * Text input for sending messages with validation
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Send, Square, X, CornerDownRight, Plus, FileText, Image as ImageIcon } from 'lucide-react';
import { message, Tooltip } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { useChatStore } from '@/store/chat';
import { useStyles } from './styles';
import { normalizeDisplayMathBlocks, rehypeMathSource } from '@/utils/markdownMath';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';

/** Maximum allowed message length */
const MAX_MESSAGE_LENGTH = 4000;
/** Warning threshold for character count */
const MAX_ATTACHMENT_COUNT = 5;
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const SUPPORTED_ATTACHMENT_TYPES = new Set([
  'image/png', 'image/jpeg', 'image/webp', 'image/gif',
  'application/pdf', 'text/plain', 'text/markdown',
]);

export interface ChatInputProps {
  /** Callback when message is sent */
  onSend: (message: string, attachments?: File[]) =>
    | void
    | { completed: boolean }
    | Promise<void | { completed: boolean }>;
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
  placeholder,
  className,
  maxLength = MAX_MESSAGE_LENGTH,
  isStreaming = false,
  onStop,
}: ChatInputProps) {
  const { styles, cx } = useStyles();
  const { t } = useUserPreferences();
  const [value, setValue] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Connect to global state for mode togglers
  const quotedText = useChatStore((state) => state.quotedText);
  const setQuotedText = useChatStore((state) => state.setQuotedText);

  const isOverLimit = value.length > maxLength;
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

  const handleSend = useCallback(async () => {
    const trimmedValue = value.trim();

    // Validation checks
    if (!trimmedValue && !quotedText && attachments.length === 0) {
      return;
    }

    if (disabled) return;

    // Check message length
    if (trimmedValue.length > maxLength) {
      message.error(t('messageTooLong', { maxLength }));
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

    try {
      const result = attachments.length > 0
        ? await onSend(finalMessage, attachments)
        : await onSend(finalMessage);

      if (result && 'completed' in result && !result.completed) return;

      setValue('');
      setAttachments([]);
      setQuotedText(null); // Clear quote after sending
    } catch {
      // Preserve text and attachments so the user can retry the request.
      return;
    }

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, attachments, disabled, onSend, maxLength, quotedText, setQuotedText, t]);

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
      message.error(t('maxAttachments', { count: MAX_ATTACHMENT_COUNT }));
      return;
    }

    let totalSize = 0;
    for (const attachment of candidates) {
      if (!SUPPORTED_ATTACHMENT_TYPES.has(attachment.type)) {
        message.error(t('unsupportedAttachment'));
        return;
      }
      if (attachment.size === 0) {
        message.error(t('emptyAttachment'));
        return;
      }
      if (attachment.size > MAX_ATTACHMENT_BYTES) {
        message.error(t('attachmentTooLarge'));
        return;
      }
      totalSize += attachment.size;
    }
    if (totalSize > MAX_TOTAL_ATTACHMENT_BYTES) {
      message.error(t('attachmentsTooLarge'));
      return;
    }

    setAttachments(candidates);
  }, [attachments, t]);

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
            aria-label={t('cancelQuote')}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {attachments.length > 0 && (
        <div className={styles.attachmentList} aria-label={t('pendingAttachments')}>
          {attachments.map((attachment) => (
            <div className={styles.attachmentChip} key={`${attachment.name}-${attachment.lastModified}`}>
              {attachment.type.startsWith('image/') ? <ImageIcon size={14} /> : <FileText size={14} />}
              <span title={attachment.name}>{attachment.name}</span>
              <button type="button" onClick={() => removeAttachment(attachment)} aria-label={`${t('delete')} ${attachment.name}`}>
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className={styles.inputRow} role="group" aria-label={t('messageInputRow')}>
        <Tooltip title={t('addAttachment')} color="#262626" styles={{ container: { color: '#ffffff' } }}>
          <button
            type="button"
            className={styles.attachmentButton}
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            aria-label={t('addAttachment')}
          >
            <Plus size={18} />
          </button>
        </Tooltip>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? t('askPlaceholder')}
          disabled={disabled}
          rows={1}
          maxLength={maxLength + 100}
          aria-label={t('messageTextarea')}
        />
        {isStreaming && onStop ? (
          <button
            type="button"
            className={cx(styles.sendButton, styles.stopButton)}
            onClick={onStop}
            aria-label={t('stopGenerating')}
          >
            <Square size={16} fill="currentColor" />
          </button>
        ) : (
          <button
            type="button"
            className={styles.sendButton}
            onClick={handleSend}
            disabled={!canSend}
            aria-label={t('sendMessage')}
          >
            <Send size={18} />
          </button>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,text/plain,text/markdown,.txt,.md"
        multiple
        hidden
        onChange={handleAttachmentChange}
        aria-label={t('chooseAttachment')}
      />

      {hasMath && (
        <div className={styles.mathPreview} aria-label={t('latexPreview')}>
          <div className={styles.mathPreviewLabel}>{t('formulaPreview')}</div>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }], rehypeMathSource]}
          >
            {normalizeDisplayMathBlocks(value)}
          </ReactMarkdown>
        </div>
      )}

    </div>
  );
}

export default ChatInput;
