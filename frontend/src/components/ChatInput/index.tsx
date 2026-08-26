'use client';

/**
 * ChatInput Component
 * Text input for sending messages with validation
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Send, Square, X, CornerDownRight, Plus, FileText } from 'lucide-react';
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
/** Maximum number of files that can be staged in one outgoing message. */
const MAX_ATTACHMENT_COUNT = 5;
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const SUPPORTED_ATTACHMENT_TYPES = new Set([
  'image/png', 'image/jpeg', 'image/webp', 'image/gif',
  'application/pdf', 'text/plain', 'text/markdown',
]);
const GENERIC_TEXT_UPLOAD_TYPES = new Set(['', 'application/octet-stream', 'text/plain', 'text/markdown']);
const PASTED_IMAGE_EXTENSION_BY_TYPE: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
  'image/gif': 'gif',
};

type AttachmentValidationKey =
  | 'maxAttachments'
  | 'unsupportedAttachment'
  | 'emptyAttachment'
  | 'attachmentTooLarge'
  | 'attachmentsTooLarge';

interface AttachmentPreview {
  file: File;
  objectUrl: string | null;
}

/**
 * Validates the complete staged attachment set before state changes.
 *
 * Args:
 *   currentAttachments: Files already staged in the composer.
 *   incomingAttachments: Files from picker, paste, or drag-and-drop.
 *
 * Returns:
 *   A translation key for the first validation failure, or null when accepted.
 *
 * Side effects:
 *   None.
 */
function validateAttachmentCandidates(currentAttachments: File[], incomingAttachments: File[]): AttachmentValidationKey | null {
  const candidates = [...currentAttachments, ...incomingAttachments];
  if (candidates.length > MAX_ATTACHMENT_COUNT) {
    return 'maxAttachments';
  }

  let totalSize = 0;
  for (const attachment of candidates) {
    if (!isSupportedAttachment(attachment)) {
      return 'unsupportedAttachment';
    }
    if (attachment.size === 0) {
      return 'emptyAttachment';
    }
    if (attachment.size > MAX_ATTACHMENT_BYTES) {
      return 'attachmentTooLarge';
    }
    totalSize += attachment.size;
  }

  return totalSize > MAX_TOTAL_ATTACHMENT_BYTES ? 'attachmentsTooLarge' : null;
}

function isSupportedAttachment(attachment: File): boolean {
  if (SUPPORTED_ATTACHMENT_TYPES.has(attachment.type)) return true;
  const extension = attachment.name.split('.').pop()?.toLowerCase() ?? '';
  return ['txt', 'md'].includes(extension) && GENERIC_TEXT_UPLOAD_TYPES.has(attachment.type);
}

/**
 * Checks whether a drag event carries files rather than selected text or links.
 *
 * Args:
 *   event: Native window drag event.
 *
 * Returns:
 *   True when the browser reports a file payload.
 *
 * Side effects:
 *   None.
 */
function isFileDrag(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files');
}

/**
 * Converts browser FileList values into arrays for shared validation.
 *
 * Args:
 *   files: FileList, array, null, or undefined from a browser input source.
 *
 * Returns:
 *   A plain File array.
 *
 * Side effects:
 *   None.
 */
function fileListToArray(files: FileList | File[] | null | undefined): File[] {
  return Array.from(files ?? []);
}

/**
 * Gives clipboard images deterministic File metadata before upload.
 *
 * Args:
 *   file: Browser-provided clipboard image file.
 *
 * Returns:
 *   A new File with a timestamped name and preserved MIME type.
 *
 * Side effects:
 *   Reads the current time for the generated filename.
 */
function createPastedImageFile(file: File): File {
  const extension = PASTED_IMAGE_EXTENSION_BY_TYPE[file.type] ?? 'png';
  return new File(
    [file],
    `pasted-image-${new Date().toISOString().replace(/[:.]/g, '-')}.${extension}`,
    { type: file.type, lastModified: Date.now() },
  );
}

/**
 * Extracts image files from clipboard data while ignoring pasted text.
 *
 * Args:
 *   items: Clipboard items from a paste event.
 *
 * Returns:
 *   Timestamped image files that can enter the regular attachment pipeline.
 *
 * Side effects:
 *   Reads clipboard item file handles supplied by the browser event.
 */
function clipboardImagesToFiles(items: DataTransferItemList | undefined): File[] {
  return Array.from(items ?? [])
    .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null)
    .map(createPastedImageFile);
}

/**
 * Formats byte counts for compact attachment preview cards.
 *
 * Args:
 *   bytes: File size in bytes.
 *
 * Returns:
 *   Human-readable B, KB, or MB text.
 *
 * Side effects:
 *   None.
 */
function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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
  const [attachmentPreviews, setAttachmentPreviews] = useState<AttachmentPreview[]>([]);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const internalDragRef = useRef(false);
  const attachmentPreviewsRef = useRef<AttachmentPreview[]>([]);
  
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

  useEffect(() => {
    attachmentPreviewsRef.current = attachmentPreviews;
  }, [attachmentPreviews]);

  useEffect(() => () => {
    for (const preview of attachmentPreviewsRef.current) {
      if (preview.objectUrl) URL.revokeObjectURL(preview.objectUrl);
    }
  }, []);

  const reportAttachmentError = useCallback((errorKey: AttachmentValidationKey) => {
    if (errorKey === 'maxAttachments') {
      message.error(t(errorKey, { count: MAX_ATTACHMENT_COUNT }));
      return;
    }
    message.error(t(errorKey));
  }, [t]);

  const addAttachments = useCallback((incomingAttachments: File[]) => {
    if (incomingAttachments.length === 0 || disabled) return;

    const currentFiles = attachmentPreviews.map((preview) => preview.file);
    const validationError = validateAttachmentCandidates(currentFiles, incomingAttachments);
    if (validationError) {
      reportAttachmentError(validationError);
      return;
    }

    setAttachmentPreviews((current) => [
      ...current,
      ...incomingAttachments.map((file) => ({
        file,
        objectUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
      })),
    ]);
  }, [attachmentPreviews, disabled, reportAttachmentError]);

  useEffect(() => {
    const resetDragState = () => {
      internalDragRef.current = false;
      dragDepthRef.current = 0;
      setIsDraggingFiles(false);
    };

    const handleDocumentDragStart = () => {
      internalDragRef.current = true;
      dragDepthRef.current = 0;
      setIsDraggingFiles(false);
    };

    const handleWindowDragEnter = (event: DragEvent) => {
      if (internalDragRef.current) return;
      if (!isFileDrag(event)) return;
      event.preventDefault();
      dragDepthRef.current += 1;
      if (!disabled) setIsDraggingFiles(true);
    };

    const handleWindowDragOver = (event: DragEvent) => {
      if (internalDragRef.current) return;
      if (!isFileDrag(event)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = disabled ? 'none' : 'copy';
    };

    const handleWindowDragLeave = (event: DragEvent) => {
      if (internalDragRef.current) return;
      if (!isFileDrag(event)) return;
      event.preventDefault();
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) setIsDraggingFiles(false);
    };

    const handleWindowDrop = (event: DragEvent) => {
      if (internalDragRef.current) {
        resetDragState();
        return;
      }
      if (!isFileDrag(event)) return;
      event.preventDefault();
      dragDepthRef.current = 0;
      setIsDraggingFiles(false);
      addAttachments(fileListToArray(event.dataTransfer?.files));
    };

    document.addEventListener('dragstart', handleDocumentDragStart, true);
    document.addEventListener('dragend', resetDragState, true);
    window.addEventListener('dragenter', handleWindowDragEnter);
    window.addEventListener('dragover', handleWindowDragOver);
    window.addEventListener('dragleave', handleWindowDragLeave);
    window.addEventListener('drop', handleWindowDrop);

    return () => {
      document.removeEventListener('dragstart', handleDocumentDragStart, true);
      document.removeEventListener('dragend', resetDragState, true);
      window.removeEventListener('dragenter', handleWindowDragEnter);
      window.removeEventListener('dragover', handleWindowDragOver);
      window.removeEventListener('dragleave', handleWindowDragLeave);
      window.removeEventListener('drop', handleWindowDrop);
    };
  }, [addAttachments, disabled]);

  const handleSend = useCallback(async () => {
    const trimmedValue = value.trim();

    // Validation checks
    if (!trimmedValue && !quotedText && attachmentPreviews.length === 0) {
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
      const quotePrompt = trimmedValue || t('quotedTextDefaultPrompt');
      finalMessage = `${formattedQuote}\n\n${quotePrompt}`;
    }

    try {
      const filesToSend = attachmentPreviews.map((preview) => preview.file);
      const result = filesToSend.length > 0
        ? await onSend(finalMessage, filesToSend)
        : await onSend(finalMessage);

      if (result && 'completed' in result && !result.completed) return;

      setValue('');
      for (const preview of attachmentPreviews) {
        if (preview.objectUrl) URL.revokeObjectURL(preview.objectUrl);
      }
      setAttachmentPreviews([]);
      setQuotedText(null); // Clear quote after sending
    } catch {
      // Preserve text and attachments so the user can retry the request.
      return;
    }

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, attachmentPreviews, disabled, onSend, maxLength, quotedText, setQuotedText, t]);

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
    const selected = fileListToArray(event.target.files);
    event.target.value = '';
    addAttachments(selected);
  }, [addAttachments]);

  const handlePaste = useCallback((event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const imageFiles = clipboardImagesToFiles(event.clipboardData?.items);
    if (imageFiles.length === 0) return;
    event.preventDefault();
    addAttachments(imageFiles);
  }, [addAttachments]);

  const removeAttachment = useCallback((target: AttachmentPreview) => {
    if (target.objectUrl) URL.revokeObjectURL(target.objectUrl);
    setAttachmentPreviews((current) => current.filter((preview) => preview !== target));
  }, []);

  const canSend = (value.trim().length > 0 || attachmentPreviews.length > 0) && !disabled && !isOverLimit;

  return (
    <>
    {isDraggingFiles && (
      <div className={styles.dropOverlay} role="status" aria-live="polite">
        <div className={styles.dropOverlayPanel}>
          <div className={styles.dropOverlayTitle}>{t('dropFilesTitle')}</div>
          <div className={styles.dropOverlaySubtitle}>{t('dropFilesSubtitle')}</div>
        </div>
      </div>
    )}
    <div className={cx('areqa-chat-input-shell', styles.container, className)}>
      {/* Quote Preview */}
      {quotedText && (
        <div className={cx('areqa-chat-input-quote-preview', styles.quotePreview)}>
          <CornerDownRight size={14} className={cx('areqa-chat-input-quote-arrow', styles.quoteArrow)} />
          <div className={cx('areqa-chat-input-quote-content', styles.quoteContent)}>{quotedText}</div>
          <button
            className={cx('areqa-chat-input-quote-close', styles.quoteClose)}
            onClick={() => setQuotedText(null)}
            aria-label={t('cancelQuote')}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {attachmentPreviews.length > 0 && (
        <div className={cx('areqa-chat-input-attachment-list', styles.attachmentList)} aria-label={t('pendingAttachments')}>
          {attachmentPreviews.map((preview) => {
            const { file: attachment, objectUrl } = preview;
            return (
            <div className={cx('areqa-chat-input-attachment-chip', styles.attachmentChip)} key={`${attachment.name}-${attachment.lastModified}`}>
              {objectUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={objectUrl}
                  alt={t('attachmentImagePreview')}
                  className={styles.attachmentThumbnail}
                />
              ) : (
                <FileText size={18} className={styles.attachmentFileIcon} />
              )}
              <span title={attachment.name}>
                <span>{attachment.name}</span>
                <small>{formatAttachmentSize(attachment.size)}</small>
              </span>
              <button type="button" onClick={() => removeAttachment(preview)} aria-label={`${t('delete')} ${attachment.name}`}>
                <X size={13} />
              </button>
            </div>
          );
          })}
        </div>
      )}

      <div className={cx('areqa-chat-input-row', styles.inputRow)} role="group" aria-label={t('messageInputRow')}>
        <Tooltip title={t('addAttachment')} color="#262626" styles={{ container: { color: '#ffffff' } }}>
          <button
            type="button"
            className={cx('areqa-chat-input-attachment-button', styles.attachmentButton)}
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            aria-label={t('addAttachment')}
          >
            <Plus size={18} />
          </button>
        </Tooltip>
        <textarea
          ref={textareaRef}
          className={cx('areqa-chat-input-textarea', styles.textarea)}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={placeholder ?? t('askPlaceholder')}
          disabled={disabled}
          rows={1}
          maxLength={maxLength + 100}
          aria-label={t('messageTextarea')}
        />
        {isStreaming && onStop ? (
          <button
            type="button"
            className={cx('areqa-chat-input-send-button', styles.sendButton, styles.stopButton)}
            onClick={onStop}
            aria-label={t('stopGenerating')}
          >
            <Square size={16} fill="currentColor" />
          </button>
        ) : (
          <button
            type="button"
            className={cx('areqa-chat-input-send-button', styles.sendButton)}
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
        <div className={cx('areqa-chat-input-math-preview', styles.mathPreview)} aria-label={t('latexPreview')}>
          <div className={cx('areqa-chat-input-math-preview-label', styles.mathPreviewLabel)}>{t('formulaPreview')}</div>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }], rehypeMathSource]}
          >
            {normalizeDisplayMathBlocks(value)}
          </ReactMarkdown>
        </div>
      )}

    </div>
    </>
  );
}

export default ChatInput;
