'use client';

/**
 * MessageItem Component
 * Displays a single message in the conversation
 */

import React, { memo, useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown, { Components } from 'react-markdown';
import { useVoiceReveal } from './useVoiceReveal';
import { Streamdown, type Components as StreamdownComponents } from 'streamdown';
import { createMathPlugin } from '@streamdown/math';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { ArrowLeft, Copy, Download, Maximize2, RefreshCw, Edit, CornerDownRight, ThumbsDown, ThumbsUp, ExternalLink, Trash2, X, NotebookPen, Volume2, VolumeX, Type, Heading1, Heading2, Heading3, Heading4, List, ListOrdered, Table2, Image as ImageIcon, TextQuote, Code2 } from 'lucide-react';
import { Button, Input, Modal, Tooltip, App } from 'antd';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { SuggestedQuestions } from '@/components/SuggestedQuestions';
import { Citations } from '@/components/Citations';
import { RAGStatusPanel } from '@/components/RAGStatusPanel';
import type { CitationSource } from '@/components/Citations';
import type { DisplayMessage, StreamingImageSlot } from '@/store/chat';
import type {
  AnswerBlock,
  ImageBlock,
  MessageFeedback,
  MessageFeedbackDetails,
  MessageFeedbackReason,
} from '@/database/schema';
import { useStyles } from './styles';
import { ImageGenerationLoading } from './ImageGenerationLoading';
import { normalizeDisplayMathBlocks, normalizeLooseStrongMarkers, rehypeMathSource } from '@/utils/markdownMath';
import { AttachmentCard } from './AttachmentCard';
import { AttachmentToggleList } from './AttachmentToggleList';
import { createLegacyAttachmentMetadata, splitLegacyAttachmentMarker } from '@/utils/attachments';
import { useUserPreferences, type InterfaceLanguage, type TranslationKey } from '@/contexts/UserPreferencesContext';
import { createReadAloudAudio, prepareReadAloudText } from '@/services/speech/readAloud';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';

const { TextArea } = Input;
const STREAMING_MARKDOWN_FLUSH_MS = 56;
const LEGACY_IMAGE_COMPLETION_TEXT = new Set([
  'Here is the image I created.',
  '這是為你產生的圖片。',
]);
const STREAMDOWN_MATH_PLUGIN = createMathPlugin({ singleDollarTextMath: true });
const STREAMDOWN_PLUGINS = {
  math: {
    ...STREAMDOWN_MATH_PLUGIN,
    // KaTeX must run first so the source plugin can read its MathML annotation.
    rehypePlugin: {
      plugins: [STREAMDOWN_MATH_PLUGIN.rehypePlugin, rehypeMathSource],
    },
  },
};
const STREAMDOWN_LINK_SAFETY = { enabled: false };
const MAX_PASTED_IMAGE_BYTES = 512 * 1024;

/**
 * Prepare assistant/user message Markdown for the renderer.
 *
 * Args:
 *   content: Raw Markdown stored in chat state.
 *
 * Returns:
 *   Markdown normalized for tolerant model output while preserving code spans
 *   and fenced code blocks.
 */
function normalizeMessageMarkdown(content: string): string {
  return normalizeDisplayMathBlocks(normalizeLooseStrongMarkers(content));
}

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
 * Validate image URLs separately from navigation URLs.
 *
 * PDF attachment visuals are delivered as backend-generated data URI images so
 * the uploaded file's pixels do not need a public URL. Only image data URIs are
 * accepted here; links still use the stricter navigation URL whitelist above.
 */
function isSafeImageUrl(url: string | undefined): boolean {
  if (!url) return false;
  if (/^data:image\/(?:png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/=\s]+$/i.test(url)) {
    return true;
  }
  return isSafeUrl(url);
}

/**
 * Normalize legacy Supabase Storage signed image URLs before rendering.
 *
 * Older persisted PDF visual blocks may contain Supabase REST signed paths that
 * start with `/object/sign/...` instead of `/storage/v1/object/sign/...`. The
 * backend now emits the canonical path, but the frontend keeps this
 * compatibility shim so refreshed historical conversations can still display
 * their already-saved images without requiring a data migration.
 */
function normalizeSupabaseStorageImageUrl(url: string | undefined): string {
  if (!url) return '';

  try {
    const parsedUrl = new URL(url);
    if (
      parsedUrl.protocol === 'https:' &&
      parsedUrl.hostname.endsWith('.supabase.co') &&
      parsedUrl.pathname.startsWith('/object/')
    ) {
      parsedUrl.pathname = `/storage/v1${parsedUrl.pathname}`;
      return parsedUrl.toString();
    }
  } catch {
    return url;
  }

  return url;
}

const PDF_PAGE_ATTRIBUTION_PATTERN = /^(.+?)(?:，|,)?\s*(?:第\s*)?(\d+)\s*(?:頁|页|page|Page)$/u;

/**
 * Localize backend-owned PDF visual attribution without mutating stored data.
 *
 * PDF image blocks can be saved in chat history with legacy mixed-language
 * metadata such as "uploaded PDF" or "paper.pdf，第 4 頁". The frontend keeps
 * those provider identifiers stable at rest and translates only the rendered
 * label for the active interface language.
 */
function localizePdfAttachmentCaption(
  caption: string,
  language: InterfaceLanguage,
  t: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  const match = caption.trim().match(PDF_PAGE_ATTRIBUTION_PATTERN);
  const filename = match?.[1]?.trim();
  const page = match?.[2];

  if (!filename || !page) {
    return caption;
  }

  return t('pdfPageAttribution', { filename, page });
}

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

const FEEDBACK_OPTIONS: Array<{ value: MessageFeedbackReason; labelKey: TranslationKey }> = [
  { value: 'incorrect_or_incomplete', labelKey: 'feedbackIncorrect' },
  { value: 'not_what_i_wanted', labelKey: 'feedbackNotWanted' },
  { value: 'slow_or_broken', labelKey: 'feedbackSlow' },
  { value: 'style_or_tone', labelKey: 'feedbackStyle' },
  { value: 'safety_or_legal', labelKey: 'feedbackSafety' },
  { value: 'other', labelKey: 'feedbackOther' },
];

function isMobileFeedbackViewport(): boolean {
  return window.matchMedia('(max-width: 768px)').matches;
}

function tableElementToRows(table: HTMLTableElement): string[][] {
  return Array.from(table.rows)
    .map((row) =>
      Array.from(row.cells)
        .map((cell) => (cell.innerText ?? cell.textContent ?? '').replace(/\s+/g, ' ').trim())
    );
}

function tableElementToClipboardText(table: HTMLTableElement): string {
  return tableElementToRows(table).map((row) => row.join('\t')).join('\n');
}

function escapeCsvCell(cell: string): string {
  const spreadsheetSafeCell = /^[=+\-@\t\r]/.test(cell) ? `'${cell}` : cell;
  return /[",\r\n]/.test(spreadsheetSafeCell)
    ? `"${spreadsheetSafeCell.replace(/"/g, '""')}"`
    : spreadsheetSafeCell;
}

function tableElementToCsv(table: HTMLTableElement): string {
  return tableElementToRows(table)
    .map((row) => row.map(escapeCsvCell).join(','))
    .join('\r\n');
}

function downloadCsvFile(csvText: string, filename: string): void {
  const blob = new Blob([`\uFEFF${csvText}`], { type: 'text/csv;charset=utf-8' });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

/**
 * Throttle high-frequency text updates while preserving the final value.
 *
 * Args:
 *   value: Latest streaming value from the chat store.
 *   delayMs: Minimum interval between rendered updates.
 *
 * Returns:
 *   A display value updated at a stable cadence. This keeps markdown parsing
 *   from running on every token packet while still flushing the final packet.
 */
function useThrottledValue<T>(value: T, delayMs: number): T {
  const [throttledValue, setThrottledValue] = React.useState(value);
  const lastFlushRef = React.useRef(0);
  const pendingValueRef = React.useRef(value);

  React.useEffect(() => {
    pendingValueRef.current = value;
    const now = window.performance.now();
    const elapsed = now - lastFlushRef.current;

    if (elapsed >= delayMs) {
      lastFlushRef.current = now;
      setThrottledValue(value);
      return undefined;
    }

    const timer = window.setTimeout(() => {
      lastFlushRef.current = window.performance.now();
      setThrottledValue(pendingValueRef.current);
    }, delayMs - elapsed);

    return () => window.clearTimeout(timer);
  }, [delayMs, value]);

  return throttledValue;
}

/**
 * Preserve the live-stream rendering mode after the terminal SSE packet.
 *
 * Args:
 *   isStreaming: Whether this mounted message is currently receiving content.
 *
 * Returns:
 *   True once this component instance has participated in a live stream.
 *
 * Side Effects:
 *   Stores a mount-local flag. This is intentionally not persisted because
 *   reloaded historical messages should use the normal static structured view.
 */
function useHasLiveStreamed(isStreaming?: boolean): boolean {
  const [hasLiveStreamed, setHasLiveStreamed] = React.useState(Boolean(isStreaming));

  React.useEffect(() => {
    if (isStreaming) {
      setHasLiveStreamed(true);
    }
  }, [isStreaming]);

  return hasLiveStreamed;
}

/**
 * Extract plain text from markdown-rendered React nodes.
 *
 * Args:
 *   node: React children supplied by a Markdown renderer.
 *
 * Returns:
 *   Concatenated text content suitable for clipboard operations.
 */
function reactNodeToPlainText(node: React.ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(reactNodeToPlainText).join('');
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return reactNodeToPlainText(node.props.children);
  }
  return '';
}

function getCodeBlockLanguage(children: React.ReactNode): string {
  const candidates = React.Children.toArray(children);
  for (const candidate of candidates) {
    if (!React.isValidElement<{ className?: string }>(candidate)) continue;
    const language = candidate.props.className?.match(/(?:^|\s)language-([^\s]+)/)?.[1];
    if (language) return language;
  }
  return 'text';
}

function MarkdownCodeBlock({
  children,
  className,
  node,
  ...props
}: React.HTMLAttributes<HTMLPreElement> & { node?: unknown }) {
  void node;
  const [copied, setCopied] = React.useState(false);
  const language = getCodeBlockLanguage(children);
  const codeText = React.useMemo(
    () => reactNodeToPlainText(children).replace(/\n$/, ''),
    [children],
  );

  const copyCode = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(codeText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }, [codeText]);

  return (
    <div className="areqa-markdown-code-frame">
      <div className="areqa-markdown-code-header">
        <span className="areqa-markdown-code-language">{language}</span>
        <Tooltip title={copied ? '已複製' : '複製'}>
          <button
            aria-label={`複製 ${language} 文字區塊`}
            className="areqa-markdown-code-copy"
            type="button"
            onClick={copyCode}
          >
            <Copy size={16} aria-hidden="true" />
          </button>
        </Tooltip>
      </div>
      <pre className={['areqa-markdown-code-block', className].filter(Boolean).join(' ')} {...props}>
        {children}
      </pre>
    </div>
  );
}

type MarkdownTableProps = React.TableHTMLAttributes<HTMLTableElement> & {
  enableActions: boolean;
  onCopyTable: (tableText: string) => void;
  onDownloadTable: (csvText: string) => void;
  modalRootClassName: string;
  labels: {
    actions: string;
    copy: string;
    downloadCsv: string;
    expand: string;
    scrollable: string;
    title: string;
    close: string;
  };
};

function MarkdownTable({
  children,
  className,
  enableActions,
  onCopyTable,
  onDownloadTable,
  modalRootClassName,
  labels,
  ...props
}: MarkdownTableProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const tableRef = React.useRef<HTMLTableElement>(null);
  const tableClassName = ['areqa-markdown-table', className].filter(Boolean).join(' ');

  const copyTable = React.useCallback(() => {
    const table = tableRef.current;
    onCopyTable(table ? tableElementToClipboardText(table) : '');
  }, [onCopyTable]);

  const downloadTable = React.useCallback(() => {
    const table = tableRef.current;
    onDownloadTable(table ? tableElementToCsv(table) : '');
  }, [onDownloadTable]);

  React.useEffect(() => {
    if (!isExpanded || typeof document === 'undefined') return undefined;

    const previousOverflow = document.body.style.overflow;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsExpanded(false);
      }
    };

    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isExpanded]);

  const actionButtons = enableActions ? (
    <div className="areqa-markdown-table-actions" aria-label={labels.actions}>
      <Tooltip title={labels.copy}>
        <button
          aria-label={labels.copy}
          className="areqa-markdown-table-action"
          type="button"
          onClick={copyTable}
        >
          <Copy size={16} aria-hidden="true" />
        </button>
      </Tooltip>
      <Tooltip title={labels.downloadCsv}>
        <button
          aria-label={labels.downloadCsv}
          className="areqa-markdown-table-action"
          type="button"
          onClick={downloadTable}
        >
          <Download size={16} aria-hidden="true" />
        </button>
      </Tooltip>
      <Tooltip title={labels.expand}>
        <button
          aria-label={labels.expand}
          className="areqa-markdown-table-action"
          type="button"
          onClick={() => setIsExpanded(true)}
        >
          <Maximize2 size={16} aria-hidden="true" />
        </button>
      </Tooltip>
    </div>
  ) : null;

  const expandedTableModal = isExpanded && typeof document !== 'undefined'
    ? createPortal(
        // The modal is portaled to the document root so transformed message bubbles
        // cannot redefine its fixed-position containing block.
        <div className={modalRootClassName}>
          <div
            aria-label={labels.title}
            aria-modal="true"
            className="areqa-markdown-table-modal-backdrop"
            role="dialog"
            onMouseDown={() => setIsExpanded(false)}
          >
            <div
              className="areqa-markdown-table-modal-panel"
              onMouseDown={(event) => event.stopPropagation()}
            >
              <div className="areqa-markdown-table-modal-header">
                <h2>{labels.title}</h2>
                <button
                  aria-label={labels.close}
                  className="areqa-markdown-table-modal-close"
                  type="button"
                  onClick={() => setIsExpanded(false)}
                >
                  <X size={24} aria-hidden="true" strokeWidth={1.8} />
                </button>
              </div>
              <div className="areqa-markdown-table-modal-body" tabIndex={0}>
                <table className={tableClassName} {...props}>
                  {children}
                </table>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )
    : null;

  return (
    <>
      <div className="areqa-markdown-table-frame">
        <div
          aria-label={labels.scrollable}
          className="areqa-markdown-table-scroll"
          tabIndex={0}
        >
          <table ref={tableRef} className={tableClassName} {...props}>
            {children}
          </table>
        </div>
        {actionButtons}
      </div>
      {expandedTableModal}
    </>
  );
}

const createMarkdownComponents = (
  messageId: string,
  enableMathCopy: boolean,
  onCopyMath: (latex: string) => void,
  onCopyTable: (tableText: string) => void,
  onDownloadTable: (csvText: string) => void,
  tableLabels: MarkdownTableProps['labels'],
  formulaCopyLabel: string,
  tableModalRootClassName: string,
): Components => ({
  strong: ({ children, node, ...props }) => {
    void node;
    return <strong {...props}>{children}</strong>;
  },
  em: ({ children, node, ...props }) => {
    void node;
    return <em {...props}>{children}</em>;
  },
  pre: ({ children, className, node, ...props }) => {
    return (
      <MarkdownCodeBlock className={className} node={node} {...props}>
        {children}
      </MarkdownCodeBlock>
    );
  },
  code: ({ children, className, node, ...props }) => {
    void node;
    return <code className={className} {...props}>{children}</code>;
  },
  table: ({ children, className, node, ...props }) => {
    void node;

    return (
      <MarkdownTable
        className={className}
        enableActions={enableMathCopy}
        onCopyTable={onCopyTable}
        onDownloadTable={onDownloadTable}
        modalRootClassName={tableModalRootClassName}
        labels={tableLabels}
        {...props}
      >
        {children}
      </MarkdownTable>
    );
  },
  // Sanitize links - only allow safe protocols
  a: ({ href, children, ...props }) => {
    if (href?.startsWith('#cite-')) {
      const citeIndex = parseInt(href.replace('#cite-', ''), 10);
      return (
        <a 
          href={href}
          onClick={(e) => {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent(`open-citation-${messageId}`, { detail: { index: citeIndex } }));
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--areqa-citation-hover-background)';
            e.currentTarget.style.borderColor = 'var(--areqa-citation-hover-border)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--areqa-citation-background)';
            e.currentTarget.style.borderColor = 'var(--areqa-citation-border)';
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: '20px',
            height: '20px',
            padding: '0 4px',
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--areqa-citation-color)',
            backgroundColor: 'var(--areqa-citation-background)',
            border: '1px solid var(--areqa-citation-border)',
            borderRadius: '4px',
            cursor: 'pointer',
            margin: '0 4px',
            verticalAlign: 'middle',
            transform: 'translateY(-1px)',
            textDecoration: 'none',
            transition: 'all 0.2s ease',
          }}
        >
          {citeIndex}
        </a>
      );
    }
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
  span: ({ className, children, node, ...props }) => {
    void node;
    const latex = (props as Record<string, unknown>)['data-latex'];
    const isDisplayMath = className === 'katex-display';

    if (enableMathCopy && isDisplayMath && typeof latex === 'string') {
      return (
        <span
          className={className}
          {...props}
          style={{ display: 'block', position: 'relative', ...((props as { style?: React.CSSProperties }).style || {}) }}
        >
          {children}
          <button
            type="button"
            aria-label={formulaCopyLabel}
            onClick={() => onCopyMath(latex)}
            style={{
              display: 'block',
              margin: '6px 0 0 auto',
              padding: '3px 8px',
              border: '1px solid rgba(216, 162, 92, 0.45)',
              borderRadius: '4px',
              background: 'rgba(216, 162, 92, 0.12)',
              color: '#d8a25c',
              cursor: 'pointer',
              fontSize: '11px',
            }}
          >
            {formulaCopyLabel}
          </button>
        </span>
      );
    }

    return <span className={className} {...props}>{children}</span>;
  },
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
  /** Callback when deleting the latest assistant turn is requested */
  onDeleteLatestTurn?: (assistantMessageId: string) => void;
  /** Callback when this assistant response should be saved as a note */
  onAddNote?: (assistantMessageId: string) => void;
  /** Whether this assistant response is already saved as a note */
  isSavedNote?: boolean;
  /** Callback when edit is submitted */
  onEdit?: (messageId: string, newContent: string) => Promise<void> | void;
  /** Callback when assistant feedback is changed */
  onFeedback?: (
    messageId: string,
    feedback: MessageFeedback | null,
    details?: MessageFeedbackDetails
  ) => Promise<void> | void;
  /** Whether this is the last message in the list (to show suggested questions) */
  isLast?: boolean;
  /** Callback when a suggested question is clicked */
  onSelectSuggestion?: (question: string) => void;
  /** Optional class name for custom styling */
  className?: string;
}

function editingTextareaRows(content: string): number {
  return Math.max(3, Math.min(18, content.split(/\r?\n/).length + 1));
}

function insertTextAtSelection(
  content: string,
  insertion: string,
  selectionStart?: number | null,
  selectionEnd?: number | null,
): string {
  const start = selectionStart ?? content.length;
  const end = selectionEnd ?? start;
  return `${content.slice(0, start)}${insertion}${content.slice(end)}`;
}

function escapeEditorHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function unescapeEditorHtml(value: string): string {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = value;
  return textarea.value;
}

function escapeMarkdownTableCell(value: string): string {
  return value.replace(/\|/g, '\\|').replace(/\r?\n/g, ' ').trim();
}

function isMarkdownTableSeparator(line: string): boolean {
  const cells = parseMarkdownTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

export function parseMarkdownTableRow(line: string): string[] {
  const source = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  const cells: string[] = [];
  let cell = '';
  let isEscaped = false;

  Array.from(source).forEach((char) => {
    if (isEscaped) {
      cell += char;
      isEscaped = false;
      return;
    }
    if (char === '\\') {
      isEscaped = true;
      return;
    }
    if (char === '|') {
      cells.push(cell.trim());
      cell = '';
      return;
    }
    cell += char;
  });
  if (isEscaped) cell += '\\';
  cells.push(cell.trim());
  return cells;
}

export function inlineMarkdownToEditorHtml(markdown: string): string {
  const placeholders: string[] = [];
  const store = (html: string) => {
    const token = `\uE000${placeholders.length}\uE001`;
    placeholders.push(html);
    return token;
  };
  let text = markdown
    .replace(/`([^`\n]+)`/g, (_match, code) => store(`<code>${escapeEditorHtml(code)}</code>`))
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (match, alt, src) => (
      isSafeImageUrl(src)
        ? store(`<img src="${escapeEditorHtml(src)}" alt="${escapeEditorHtml(alt)}" />`)
        : match
    ))
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, href) => (
      isSafeUrl(href)
        ? store(`<a href="${escapeEditorHtml(href)}">${escapeEditorHtml(label)}</a>`)
        : match
    ));

  text = escapeEditorHtml(text);
  text = text
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^\w])__([^_\n]+)__(?=$|[^\w])/g, '$1<strong>$2</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/(^|[^\w])_([^_\n]+)_(?=$|[^\w])/g, '$1<em>$2</em>');

  placeholders.forEach((html, index) => {
    text = text.replace(new RegExp(`\\uE000${index}\\uE001`, 'g'), html);
  });
  return text;
}

export function markdownToEditorHtml(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const html: string[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fenceMatch = line.match(/^```([\w-]*)\s*$/);
    if (fenceMatch) {
      const language = fenceMatch[1] || '';
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index] ?? '')) {
        codeLines.push(lines[index] ?? '');
        index += 1;
      }
      if (index < lines.length) index += 1;
      html.push(`<pre><code${language ? ` data-language="${escapeEditorHtml(language)}"` : ''}>${escapeEditorHtml(codeLines.join('\n'))}</code></pre>`);
      continue;
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      html.push(`<h${level}>${inlineMarkdownToEditorHtml(headingMatch[2])}</h${level}>`);
      index += 1;
      continue;
    }

    const imageMatch = line.trim().match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch && isSafeImageUrl(imageMatch[2])) {
      html.push(`<figure data-md-image="true"><img src="${escapeEditorHtml(imageMatch[2])}" alt="${escapeEditorHtml(imageMatch[1])}" /><figcaption>${escapeEditorHtml(imageMatch[1])}</figcaption></figure>`);
      index += 1;
      continue;
    }

    if (line.includes('|') && lines[index + 1] && isMarkdownTableSeparator(lines[index + 1])) {
      const tableRows = [parseMarkdownTableRow(line)];
      index += 2;
      while (index < lines.length && lines[index]?.includes('|') && lines[index]?.trim()) {
        tableRows.push(parseMarkdownTableRow(lines[index]));
        index += 1;
      }
      const [headerRow, ...bodyRows] = tableRows;
      const columnCount = Math.max(...tableRows.map((row) => row.length));
      const normalizedHeader = [...headerRow, ...Array.from({ length: columnCount - headerRow.length }, () => '')];
      const normalizedBodyRows = bodyRows.map((row) => [...row, ...Array.from({ length: columnCount - row.length }, () => '')]);
      html.push('<table><thead><tr>');
      normalizedHeader.forEach((cell) => html.push(`<th>${inlineMarkdownToEditorHtml(cell)}</th>`));
      html.push('</tr></thead><tbody>');
      normalizedBodyRows.forEach((row) => {
        html.push('<tr>');
        row.forEach((cell) => html.push(`<td>${inlineMarkdownToEditorHtml(cell)}</td>`));
        html.push('</tr>');
      });
      html.push('</tbody></table>');
      continue;
    }

    const listMatch = line.match(/^(\s*)([-*+]|\d+\.)\s+(.+)$/);
    if (listMatch) {
      const ordered = /\d+\./.test(listMatch[2]);
      const tag = ordered ? 'ol' : 'ul';
      html.push(`<${tag}>`);
      while (index < lines.length) {
        const itemMatch = lines[index]?.match(/^(\s*)([-*+]|\d+\.)\s+(.+)$/);
        if (!itemMatch || /\d+\./.test(itemMatch[2]) !== ordered) break;
        const depth = Math.floor(itemMatch[1].replace(/\t/g, '  ').length / 2);
        html.push(`<li data-depth="${depth}">${inlineMarkdownToEditorHtml(itemMatch[3])}</li>`);
        index += 1;
      }
      html.push(`</${tag}>`);
      continue;
    }

    if (line.startsWith('>')) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index]?.startsWith('>')) {
        quoteLines.push(lines[index].replace(/^>\s?/, ''));
        index += 1;
      }
      html.push(`<blockquote>${inlineMarkdownToEditorHtml(quoteLines.join('\n')).replace(/\n/g, '<br />')}</blockquote>`);
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (
      index < lines.length &&
      lines[index]?.trim() &&
      !/^(#{1,4})\s+/.test(lines[index]) &&
      !/^```([\w-]*)\s*$/.test(lines[index] ?? '') &&
      !/^(\s*)([-*+]|\d+\.)\s+/.test(lines[index]) &&
      !(lines[index]?.includes('|') && lines[index + 1] && isMarkdownTableSeparator(lines[index + 1])) &&
      !/^!\[([^\]]*)\]\(([^)]+)\)$/.test(lines[index].trim()) &&
      !lines[index]?.startsWith('>')
    ) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    html.push(`<p>${inlineMarkdownToEditorHtml(paragraphLines.join('\n')).replace(/\n/g, '<br />')}</p>`);
  }

  return html.join('') || '<p><br /></p>';
}

function elementTextWithBreaks(element: Element): string {
  return Array.from(element.childNodes)
    .map((node) => {
      if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? '';
      if (node.nodeType !== Node.ELEMENT_NODE) return '';
      const child = node as HTMLElement;
      if (child.tagName === 'BR') return '\n';
      return child.innerText ?? child.textContent ?? '';
    })
    .join('');
}

function inlineNodeToMarkdown(node: Node, options: { skipNestedLists?: boolean } = {}): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? '';
  if (node.nodeType !== Node.ELEMENT_NODE) return '';

  const element = node as HTMLElement;
  if (options.skipNestedLists && (element.tagName === 'UL' || element.tagName === 'OL')) return '';
  const children = Array.from(element.childNodes).map((child) => inlineNodeToMarkdown(child, options)).join('');
  switch (element.tagName) {
    case 'STRONG':
    case 'B':
      return children.trim() ? `**${children}**` : '';
    case 'EM':
    case 'I':
      return children.trim() ? `*${children}*` : '';
    case 'CODE':
      return children.trim() ? `\`${children}\`` : '';
    case 'A': {
      const href = unescapeEditorHtml(element.getAttribute('href') ?? '');
      return href && isSafeUrl(href) ? `[${children || href}](${href})` : children;
    }
    case 'IMG': {
      const src = element.getAttribute('src') ?? '';
      const alt = element.getAttribute('alt') ?? '';
      return src && isSafeImageUrl(src) ? `![${alt}](${src})` : '';
    }
    case 'BR':
      return '\n';
    default:
      return children;
  }
}

function inlineElementToMarkdown(element: Element, options: { skipNestedLists?: boolean } = {}): string {
  return Array.from(element.childNodes).map((node) => inlineNodeToMarkdown(node, options)).join('').replace(/\u00a0/g, ' ');
}

function listItemToMarkdown(item: HTMLLIElement, ordered: boolean, index: number, depth: number): string[] {
  const marker = ordered ? `${index + 1}.` : '-';
  const line = `${'  '.repeat(depth)}${marker} ${inlineElementToMarkdown(item, { skipNestedLists: true }).trim()}`.trimEnd();
  const nestedLines = Array.from(item.children)
    .filter((child) => child.tagName === 'UL' || child.tagName === 'OL')
    .flatMap((nestedList) => listElementToMarkdown(nestedList as HTMLOListElement | HTMLUListElement, depth + 1));
  return [line, ...nestedLines].filter((value) => value.trim().length > 1);
}

function listElementToMarkdown(element: HTMLOListElement | HTMLUListElement, depth = 0): string[] {
  const ordered = element.tagName === 'OL';
  return Array.from(element.children)
    .filter((child): child is HTMLLIElement => child.tagName === 'LI')
    .flatMap((item, index) => {
      const visualDepth = depth + Number(item.dataset.depth ?? 0);
      return listItemToMarkdown(item, ordered, index, visualDepth);
    });
}

function hasMarkdownBlockDescendant(element: Element): boolean {
  return Array.from(element.children).some((child) => (
    /^(H[1-4]|UL|OL|TABLE|FIGURE|BLOCKQUOTE|PRE|P|DIV|SECTION|ARTICLE)$/.test(child.tagName) ||
    hasMarkdownBlockDescendant(child)
  ));
}

function nodeToMarkdownBlocks(node: Node): string[] {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = (node.textContent ?? '').trim();
    return text ? [text] : [];
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return [];
  return elementToMarkdownBlocks(node as HTMLElement);
}

function elementToMarkdownBlocks(element: HTMLElement): string[] {
  const text = inlineElementToMarkdown(element).trim();

  if (/^H[1-4]$/.test(element.tagName)) {
    const level = Number(element.tagName.slice(1));
    return text ? [`${'#'.repeat(level)} ${text}`] : [];
  }

  if (element.tagName === 'UL' || element.tagName === 'OL') {
    const lines = listElementToMarkdown(element as HTMLOListElement | HTMLUListElement);
    return lines.length ? [lines.join('\n')] : [];
  }

  if (element.tagName === 'TABLE') {
    const rows = Array.from((element as HTMLTableElement).rows)
      .map((row) => Array.from(row.cells).map((cell) => escapeMarkdownTableCell(inlineElementToMarkdown(cell))));
    if (!rows.length) return [];
    const columnCount = Math.max(...rows.map((row) => row.length));
    const normalizedRows = rows.map((row) => [...row, ...Array.from({ length: columnCount - row.length }, () => '')]);
    return [[
      `| ${normalizedRows[0].join(' | ')} |`,
      `| ${Array.from({ length: columnCount }, () => '---').join(' | ')} |`,
      ...normalizedRows.slice(1).map((row) => `| ${row.join(' | ')} |`),
    ].join('\n')];
  }

  if (element.tagName === 'FIGURE') {
    const image = element.querySelector('img');
    const src = image?.getAttribute('src') ?? '';
    const caption = element.querySelector('figcaption');
    const alt = caption ? inlineElementToMarkdown(caption).trim() : image?.getAttribute('alt') ?? elementTextWithBreaks(element).trim();
    return src && isSafeImageUrl(src) ? [`![${alt}](${src})`] : [];
  }

  if (element.tagName === 'BLOCKQUOTE') {
    const quote = inlineElementToMarkdown(element).trim();
    return quote ? [quote.split('\n').map((line) => `> ${line}`).join('\n')] : [];
  }

  if (element.tagName === 'PRE') {
    const code = element.querySelector('code');
    const language = code?.getAttribute('data-language') ?? '';
    const codeText = code?.textContent ?? element.textContent ?? '';
    return [`\`\`\`${language}\n${codeText.replace(/\n$/, '')}\n\`\`\``];
  }

  if (element.tagName === 'IMG') {
    const src = element.getAttribute('src') ?? '';
    const alt = element.getAttribute('alt') ?? '';
    return src && isSafeImageUrl(src) ? [`![${alt}](${src})`] : [];
  }

  if (hasMarkdownBlockDescendant(element)) {
    return Array.from(element.childNodes).flatMap(nodeToMarkdownBlocks);
  }

  return text ? [text] : [];
}

/**
 * Converts the rich assistant editor DOM back to Markdown.
 *
 * Browser editing commands can wrap pasted or edited blocks in neutral elements
 * such as divs. The serializer walks nested block descendants so those wrappers
 * do not flatten lists, tables, quotes, or code blocks into plain text.
 */
export function editorHtmlToMarkdown(root: HTMLElement): string {
  const blocks = Array.from(root.childNodes).flatMap(nodeToMarkdownBlocks);
  return blocks.join('\n\n').trim();
}

function selectionBelongsToEditor(editor: HTMLElement, selection: Selection | null): selection is Selection {
  if (!selection?.rangeCount) return false;
  const range = selection.getRangeAt(0);
  return editor.contains(range.startContainer) && editor.contains(range.endContainer);
}

function getActiveSlashRange(editor: HTMLElement): Range | null {
  const selection = window.getSelection();
  if (!selectionBelongsToEditor(editor, selection) || !selection.isCollapsed) return null;

  const range = selection.getRangeAt(0);
  if (range.startContainer.nodeType !== Node.TEXT_NODE) return null;

  const textNode = range.startContainer;
  const textBeforeCaret = (textNode.textContent ?? '').slice(0, range.startOffset);
  const slashMatch = textBeforeCaret.match(/(^|\s)\/[\w-]*$/);
  if (!slashMatch) return null;

  const slashRange = document.createRange();
  slashRange.setStart(textNode, textBeforeCaret.length - slashMatch[0].trimStart().length);
  slashRange.setEnd(textNode, range.startOffset);
  return slashRange;
}

function getTrailingSlashRange(editor: HTMLElement): Range | null {
  const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
  let lastTextNode: Text | null = null;
  while (walker.nextNode()) {
    lastTextNode = walker.currentNode as Text;
  }
  const text = lastTextNode?.textContent ?? '';
  const slashMatch = text.match(/(^|\s)\/[\w-]*$/);
  if (!lastTextNode || !slashMatch) return null;

  const slashRange = document.createRange();
  slashRange.setStart(lastTextNode, text.length - slashMatch[0].trimStart().length);
  slashRange.setEnd(lastTextNode, text.length);
  return slashRange;
}

function removeSlashTrigger(editor: HTMLElement, slashRange: Range | null): HTMLElement | null {
  if (!slashRange || !editor.contains(slashRange.startContainer)) return null;
  const targetBlock = closestEditableBlock(slashRange.startContainer, editor);

  if (
    slashRange.startContainer === slashRange.endContainer &&
    slashRange.startContainer.nodeType === Node.TEXT_NODE
  ) {
    const textNode = slashRange.startContainer;
    const text = textNode.textContent ?? '';
    textNode.textContent = `${text.slice(0, slashRange.startOffset)}${text.slice(slashRange.endOffset)}`;
    const selection = window.getSelection();
    const nextOffset = Math.min(slashRange.startOffset, textNode.textContent.length);
    const nextRange = document.createRange();
    nextRange.setStart(textNode, nextOffset);
    nextRange.collapse(true);
    selection?.removeAllRanges();
    selection?.addRange(nextRange);
    return targetBlock;
  }

  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(slashRange);
  slashRange.deleteContents();
  return targetBlock;
}

function removeDanglingSlashTriggerBlocks(editor: HTMLElement): void {
  Array.from(editor.querySelectorAll('p,li,blockquote,h1,h2,h3,h4')).forEach((block) => {
    if (/^\/[\w-]*$/.test(elementTextWithBreaks(block).trim())) {
      block.remove();
    }
  });
}

function placeCaretAtEnd(element: Node): void {
  const selection = window.getSelection();
  if (!selection) return;
  const range = document.createRange();
  range.selectNodeContents(element);
  range.collapse(false);
  selection.removeAllRanges();
  selection.addRange(range);
}

function htmlFragmentFromMarkdown(markdown: string): DocumentFragment {
  const template = document.createElement('template');
  template.innerHTML = markdownToEditorHtml(markdown);
  return template.content;
}

function insertFragmentNearSelection(editor: HTMLElement, fragment: DocumentFragment): Node | null {
  const selection = window.getSelection();
  if (!selectionBelongsToEditor(editor, selection)) {
    const firstNode = fragment.firstChild;
    editor.appendChild(fragment);
    return firstNode;
  }

  const range = selection.getRangeAt(0);
  range.deleteContents();
  const firstNode = fragment.firstChild;
  const lastNode = fragment.lastChild;
  range.insertNode(fragment);
  if (lastNode) {
    range.setStartAfter(lastNode);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
  }
  return firstNode;
}

type AssistantRichMarkdownEditorProps = {
  value: string;
  disabled: boolean;
  label: string;
  className: string;
  menuClassName: string;
  menuItemClassName: string;
  onChange: (value: string) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => void;
  onPaste: (event: React.ClipboardEvent<HTMLDivElement>) => void;
};

type SlashCommandMenuItem = {
  label: string;
  icon: React.ReactNode;
  markdown: string;
};

function isBlockFragment(fragment: DocumentFragment): boolean {
  return Array.from(fragment.children).some((child) => /^(P|H[1-6]|UL|OL|TABLE|FIGURE|BLOCKQUOTE|PRE)$/.test(child.tagName));
}

function closestEditableBlock(node: Node, editor: HTMLElement): HTMLElement | null {
  const element = node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
  const block = element?.closest('p,h1,h2,h3,h4,li,blockquote,pre');
  return block instanceof HTMLElement && editor.contains(block) ? block : null;
}

function AssistantRichMarkdownEditor({
  value,
  disabled,
  label,
  className,
  menuClassName,
  menuItemClassName,
  onChange,
  onKeyDown,
  onPaste,
}: AssistantRichMarkdownEditorProps) {
  const editorRef = React.useRef<HTMLDivElement | null>(null);
  const activeSlashRangeRef = React.useRef<Range | null>(null);
  const lastInputMarkdownRef = React.useRef<string | null>(null);
  const hasFocusedRef = React.useRef(false);
  const [isMenuOpen, setIsMenuOpen] = React.useState(false);
  const [menuPosition, setMenuPosition] = React.useState({ top: 0, left: 0 });

  React.useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (document.activeElement === editor && value === lastInputMarkdownRef.current) return;
    editor.innerHTML = markdownToEditorHtml(value);
    if (!hasFocusedRef.current) {
      hasFocusedRef.current = true;
      window.setTimeout(() => editor.focus(), 0);
    }
  }, [value]);

  const syncMarkdown = React.useCallback(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const nextMarkdown = editorHtmlToMarkdown(editor);
    lastInputMarkdownRef.current = nextMarkdown;
    onChange(nextMarkdown);
  }, [onChange]);

  const insertMarkdownBlock = React.useCallback((markdownBlock: string) => {
    const editor = editorRef.current;
    if (!editor) return;

    const slashRange = getActiveSlashRange(editor) ?? activeSlashRangeRef.current ?? getTrailingSlashRange(editor);
    const slashBlock = removeSlashTrigger(editor, slashRange);
    activeSlashRangeRef.current = null;

    const selection = window.getSelection();
    const range = selectionBelongsToEditor(editor, selection) ? selection.getRangeAt(0) : null;
    const fragment = htmlFragmentFromMarkdown(markdownBlock);
    const lastNode = fragment.lastChild;
    const targetBlock = slashBlock ?? (range ? closestEditableBlock(range.startContainer, editor) : null);

    if (targetBlock && isBlockFragment(fragment)) {
      if (elementTextWithBreaks(targetBlock).trim()) {
        targetBlock.after(fragment);
      } else {
        targetBlock.replaceWith(fragment);
      }
      if (lastNode) placeCaretAtEnd(lastNode);
    } else {
      const insertedNode = insertFragmentNearSelection(editor, fragment);
      if (insertedNode) placeCaretAtEnd(insertedNode);
    }

    removeDanglingSlashTriggerBlocks(editor);
    const nextMarkdown = editorHtmlToMarkdown(editor);
    lastInputMarkdownRef.current = nextMarkdown;
    onChange(nextMarkdown);
    setIsMenuOpen(false);
    window.setTimeout(() => editor.focus(), 0);
  }, [onChange]);

  const updateSlashMenu = React.useCallback(() => {
    const editor = editorRef.current;
    const selection = window.getSelection();
    if (!editor || !selectionBelongsToEditor(editor, selection) || !selection.isCollapsed) {
      setIsMenuOpen(false);
      activeSlashRangeRef.current = null;
      return;
    }

    const slashRange = getActiveSlashRange(editor);
    if (!slashRange) {
      setIsMenuOpen(false);
      activeSlashRangeRef.current = null;
      return;
    }

    activeSlashRangeRef.current = slashRange.cloneRange();
    const editorRect = editor.getBoundingClientRect();
    const caretRange = selection.getRangeAt(0).cloneRange();
    const caretRect = typeof caretRange.getBoundingClientRect === 'function'
      ? caretRange.getBoundingClientRect()
      : editorRect;
    setMenuPosition({
      top: Math.max(0, caretRect.bottom - editorRect.top + 6),
      left: Math.max(0, Math.min(caretRect.left - editorRect.left, editorRect.width - 304)),
    });
    setIsMenuOpen(true);
  }, []);

  const handleInput = React.useCallback(() => {
    syncMarkdown();
    updateSlashMenu();
  }, [syncMarkdown, updateSlashMenu]);

  const menuItems: SlashCommandMenuItem[] = [
    { label: 'Text', icon: <Type size={16} aria-hidden="true" />, markdown: '新段落' },
    { label: 'Heading 1', icon: <Heading1 size={16} aria-hidden="true" />, markdown: '# 新標題' },
    { label: 'Heading 2', icon: <Heading2 size={16} aria-hidden="true" />, markdown: '## 新標題' },
    { label: 'Heading 3', icon: <Heading3 size={16} aria-hidden="true" />, markdown: '### 新標題' },
    { label: 'Heading 4', icon: <Heading4 size={16} aria-hidden="true" />, markdown: '#### 新標題' },
    { label: 'Bulleted list', icon: <List size={16} aria-hidden="true" />, markdown: '- 清單項目' },
    { label: 'Numbered list', icon: <ListOrdered size={16} aria-hidden="true" />, markdown: '1. 清單項目' },
    { label: 'Quote', icon: <TextQuote size={16} aria-hidden="true" />, markdown: '> 引用內容' },
    { label: 'Code', icon: <Code2 size={16} aria-hidden="true" />, markdown: '```\n程式碼\n```' },
    { label: 'Table', icon: <Table2 size={16} aria-hidden="true" />, markdown: '| 欄位 A | 欄位 B | 欄位 C |\n| --- | --- | --- |\n| 內容 |  | 內容 |\n|  | 內容 |  |' },
    { label: 'Image', icon: <ImageIcon size={16} aria-hidden="true" />, markdown: '![圖片說明](https://example.com/image.png)' },
  ];

  return (
    <div className={className}>
      <div
        aria-label={label}
        aria-multiline="true"
        contentEditable={!disabled}
        data-testid="assistant-rich-editor"
        onBlur={() => window.setTimeout(() => setIsMenuOpen(false), 0)}
        onFocus={() => setIsMenuOpen(false)}
        onInput={handleInput}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && isMenuOpen) {
            event.preventDefault();
            event.stopPropagation();
            setIsMenuOpen(false);
            return;
          }
          if (event.key === 'Enter' && isMenuOpen) {
            event.preventDefault();
            insertMarkdownBlock(menuItems[0].markdown);
            return;
          }
          onKeyDown(event);
        }}
        onPaste={onPaste}
        ref={editorRef}
        role="textbox"
        suppressContentEditableWarning
        tabIndex={0}
      />
      {isMenuOpen && (
        <div
          className={menuClassName}
          role="menu"
          aria-label="Insert block"
          style={{ left: menuPosition.left, top: menuPosition.top }}
        >
          {menuItems.map((item) => (
            <button
              className={menuItemClassName}
              key={item.label}
              onClick={() => insertMarkdownBlock(item.markdown)}
              onMouseDown={(event) => {
                event.preventDefault();
                insertMarkdownBlock(item.markdown);
              }}
              role="menuitem"
              type="button"
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// New Sub-Component for handling streaming markdown parsing safely
export function normalizeCitationMarkers(content: string): string {
  let text = content;

  // Support both full-width and Markdown-style citation markers, e.g.
  // 【文獻5】 and [文獻5], while leaving regular Markdown links untouched.
  text = text.replace(/[【[]文獻([^】\]]+)[】\]](?!\()/g, (match, markerContent) => {
    const nums = markerContent.match(/\d+/g);
    if (nums) {
      return nums.map((n: string) => `[${n}](#cite-${n})`).join('');
    }
    return match;
  });

  // Also support legacy numeric markers such as [5] or [5, 6].
  return text.replace(/\[([\d\s,、]+)\](?!\()/g, (match, markerContent) => {
    const nums = markerContent.match(/\d+/g);
    if (nums) {
      return nums.map((n: string) => `[${n}](#cite-${n})`).join('');
    }
    return match;
  });
}

function StreamingMarkdown({
  content,
  markdownComponents,
  animate = false,
  voicePlayback,
  voiceCaption,
}: {
  content: string;
  markdownComponents: Components;
  animate?: boolean;
  voicePlayback?: import('@/store/chat').DisplayMessage['voicePlayback'];
  voiceCaption?: string;
}) {
  const visibleContent = useVoiceReveal(content, voicePlayback, voiceCaption);
  const isVoicePlayback = Boolean(voicePlayback);
  const throttledContent = useThrottledValue(visibleContent, STREAMING_MARKDOWN_FLUSH_MS);
  const deferredContent = React.useDeferredValue((isVoicePlayback || !animate) ? visibleContent : throttledContent);
  const processedContent = React.useMemo(() => {
    return normalizeMessageMarkdown(normalizeCitationMarkers(deferredContent));
  }, [deferredContent]);

  return (
    <Streamdown
      key={animate ? 'animated' : 'static'}
      components={markdownComponents as StreamdownComponents}
      controls={false}
      disallowedElements={['script', 'iframe', 'object', 'embed']}
      linkSafety={STREAMDOWN_LINK_SAFETY}
      mode="streaming"
      isAnimating={animate}
      animated={animate ? { animation: 'fadeIn', sep: 'char', duration: 260, stagger: 16 } : false}
      plugins={STREAMDOWN_PLUGINS}
    >
      {processedContent}
    </Streamdown>
  );
}

function getImageAspectRatio(block: ImageBlock): React.CSSProperties {
  if (!block.width || !block.height || block.width <= 0 || block.height <= 0) {
    return { aspectRatio: '16 / 9' };
  }

  const ratio = block.width / block.height;
  if (ratio < 0.75 || ratio > 2.6) {
    return { aspectRatio: '16 / 9' };
  }

  return { aspectRatio: `${block.width} / ${block.height}` };
}

/**
 * Render one verified image block inside an assistant answer.
 *
 * The backend owns retrieval and safety verification. This component keeps the
 * source attribution visible, rejects unsafe URLs before they reach the DOM,
 * and opens a viewport-level image viewer whose image/source links preserve the
 * original provider navigation path.
 */
function ImageBlockCard({ block, conversationId, styles }: { block: ImageBlock; conversationId: string; styles: ReturnType<typeof useStyles>['styles'] }) {
  const { language, t } = useUserPreferences();
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);
  const [isImageLoaded, setIsImageLoaded] = useState(false);
  const [imageLoadFailed, setImageLoadFailed] = useState(false);
  const [imageRetryCount, setImageRetryCount] = useState(0);
  const [renewedUrl, setRenewedUrl] = useState('');
  const [isRenewing, setIsRenewing] = useState(false);
  const [renewalFailed, setRenewalFailed] = useState(false);
  const [renewalRetryCount, setRenewalRetryCount] = useState(0);
  const isPdfAttachmentImage = block.provider === 'pdf_attachment';
  const isGeneratedImage = block.provider === 'generated_image';
  const imageUrl = normalizeSupabaseStorageImageUrl(renewedUrl || block.thumbnailUrl || block.imageUrl);
  const fullImageUrl = normalizeSupabaseStorageImageUrl(renewedUrl || block.imageUrl || block.thumbnailUrl);
  const safeImageUrl = isSafeImageUrl(imageUrl) ? imageUrl : '';
  const safeFullImageUrl = isSafeImageUrl(fullImageUrl) ? fullImageUrl : safeImageUrl;
  const safeSourceUrl = isSafeUrl(block.sourceUrl) ? block.sourceUrl : '';
  const rawDisplayCaption = block.attributionCaption || block.caption || block.topic;
  const displayCaption = isPdfAttachmentImage
    ? localizePdfAttachmentCaption(rawDisplayCaption, language, t)
    : rawDisplayCaption;
  // PDF planner metadata and generated-image prompts are not visible captions.
  // Keep generated intent available for accessibility and regeneration only.
  const displayExplanatoryCaption = isPdfAttachmentImage || isGeneratedImage ? '' : block.explanatoryCaption;
  const sourceLabel = isPdfAttachmentImage ? t('pdfAttachmentSource') : isGeneratedImage ? '' : block.sourceDomain || 'source';
  const visualStatus = block.status || (block.imageUrl ? 'resolved' : 'pending');
  const imageFrameStyle = getImageAspectRatio(block);

  React.useEffect(() => {
    if (!isGeneratedImage || !block.storagePath?.startsWith('users/') || !block.storageExpiresAt) return;
    if (renewalRetryCount === 0 && block.storageExpiresAt > Date.now() / 1000 + 300) return;
    let active = true;
    setRenewalFailed(false);
    setIsRenewing(true);
    void authenticatedFetch('/api/images/refresh', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, image_id: block.slotId }),
    }).then(async (response) => {
      if (!response.ok) throw new Error('Image URL renewal failed');
      const result = await response.json() as { imageUrl?: string };
      if (!isSafeImageUrl(result.imageUrl)) throw new Error('Invalid renewed image URL');
      if (active) setRenewedUrl(result.imageUrl || '');
    }).catch(() => {
      if (active) setRenewalFailed(true);
    }).finally(() => {
      if (active) setIsRenewing(false);
    });
    return () => { active = false; };
  }, [isGeneratedImage, block.storagePath, block.storageExpiresAt, block.slotId, conversationId, renewalRetryCount]);

  React.useEffect(() => {
    setIsImageLoaded(false);
    setImageLoadFailed(false);
  }, [safeImageUrl]);

  React.useEffect(() => {
    if (!isLightboxOpen) return;

    // The image viewer is intentionally independent of Ant Design Modal so it
    // can match the full-screen visual treatment while retaining keyboard exit.
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsLightboxOpen(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isLightboxOpen]);

  const handleGeneratedDownload = async (event: React.MouseEvent<HTMLAnchorElement>) => {
    event.stopPropagation();
    if (!block.storagePath?.startsWith('users/')) return;
    event.preventDefault();
    try {
      const response = await authenticatedFetch('/api/images/download', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: conversationId, image_id: block.slotId }),
      });
      if (!response.ok) throw new Error('Image download failed');
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = 'areqa-image.png';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch {
      window.open(safeFullImageUrl, '_blank', 'noopener,noreferrer');
    }
  };

  if (visualStatus === 'pending' || isRenewing) {
    if (isGeneratedImage) {
      const caption = isRenewing
        ? language === 'en' ? 'Loading image…' : '正在載入圖片…'
        : block.generationState === 'preparing_reference'
          ? language === 'en' ? 'Reading reference…' : '正在準備參考資料…'
          : block.generationState === 'storing'
            ? language === 'en' ? 'Saving image…' : '正在儲存圖片…'
            : block.generationState === 'generating'
              ? language === 'en' ? 'Creating image…' : '正在產生圖片…'
              : displayCaption;
      return <ImageGenerationLoading caption={caption} frameStyle={imageFrameStyle} canStop={!isRenewing} />;
    }
    return (
      <figure className={styles.answerImageCard} aria-label="圖片載入中">
        <div
          className={styles.answerImagePendingFrame}
          role="status"
          aria-label={isGeneratedImage ? (language === 'en' ? 'Creating image' : '圖片產生中') : '圖片搜尋中'}
          style={imageFrameStyle}
        >
          <div className={styles.answerImageSkeleton} data-testid="answer-image-skeleton" />
          <span className={styles.answerImagePendingLabel}>{displayCaption}</span>
        </div>
      </figure>
    );
  }

  if (renewalFailed) {
    return <div role="status">
      <p>{language === 'en' ? 'The image is temporarily unavailable.' : '圖片目前無法載入。'}</p>
      <button type="button" onClick={() => setRenewalRetryCount((count) => count + 1)}>
        {language === 'en' ? 'Retry loading image' : '重新載入圖片'}
      </button>
    </div>;
  }

  if (visualStatus === 'error') {
    return <p role="status">{displayCaption || (language === 'en' ? 'Image generation failed. Please try again.' : '產圖失敗，請重新生成。')}</p>;
  }

  if (imageLoadFailed) {
    return <div role="status">
      <p>{language === 'en' ? 'The image could not be loaded.' : '圖片載入失敗。'}</p>
      <button type="button" onClick={() => {
        setImageRetryCount((count) => count + 1);
        if (isGeneratedImage && block.storagePath?.startsWith('users/')) setRenewalRetryCount((count) => count + 1);
        setImageLoadFailed(false);
        setIsImageLoaded(false);
      }}>{language === 'en' ? 'Retry loading image' : '重新載入圖片'}</button>
    </div>;
  }

  if (!safeImageUrl || (!safeSourceUrl && !isPdfAttachmentImage && !isGeneratedImage) || block.safetyStatus !== 'pass') {
    return isGeneratedImage ? <p role="status">{language === 'en' ? 'The image is unavailable. Please try again.' : '圖片目前無法顯示，請重新生成。'}</p> : null;
  }

  return (
    <>
      {displayExplanatoryCaption && (
        <p className={styles.answerImageExplanation}>{displayExplanatoryCaption}</p>
      )}
      <figure className={`${styles.answerImageCard} ${isGeneratedImage ? styles.generatedImageCard : ''}`}>
        <button
          type="button"
          className={styles.answerImageButton}
          // Generated images use their intrinsic ratio, including when metadata is missing.
          style={isGeneratedImage ? undefined : imageFrameStyle}
          onClick={() => setIsLightboxOpen(true)}
          aria-label={t('expandImage', { caption: displayCaption })}
        >
          {!isImageLoaded && (
            <span className={styles.answerImageSkeletonLayer} aria-hidden="true" data-testid="answer-image-skeleton">
              <span className={styles.answerImageSkeleton} />
            </span>
          )}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            key={imageRetryCount}
            src={safeImageUrl}
            alt={displayCaption}
            className={`${styles.answerImage} ${isGeneratedImage ? styles.generatedImage : ''} ${isImageLoaded ? styles.answerImageLoaded : ''}`}
            loading="lazy"
            onLoad={() => setIsImageLoaded(true)}
            onError={() => {
              setImageLoadFailed(true);
              if (isGeneratedImage) logger.warn('image_generation_display_failed', { conversationId, imageId: block.slotId });
            }}
          />
        </button>
        {!isGeneratedImage && <figcaption className={`${styles.answerImageCaption} ${isImageLoaded ? styles.answerImageCaptionVisible : ''}`}>
          {!isGeneratedImage && <span className={styles.answerImageCaptionText}>{displayCaption}</span>}
          <span className={styles.answerImageMetaLine}>
            <span>{sourceLabel}</span>
            {isPdfAttachmentImage ? (
              <span>{t('uploadedAttachmentBadge')}</span>
            ) : isGeneratedImage ? null : (
              <a
                href={safeSourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.answerImageSource}
                title={block.sourceUrl}
                onClick={(event) => event.stopPropagation()}
              >
                來源
                <ExternalLink size={12} aria-hidden="true" />
              </a>
            )}
          </span>
        </figcaption>}
      </figure>
      {isLightboxOpen && createPortal(
        <div
          className={styles.answerImageLightbox}
          role="dialog"
          aria-modal="true"
          aria-label={displayCaption}
          onClick={() => setIsLightboxOpen(false)}
        >
          <button
            type="button"
            className={styles.answerImageLightboxBack}
            aria-label="關閉圖片檢視"
            onClick={() => setIsLightboxOpen(false)}
          >
            <ArrowLeft size={24} aria-hidden="true" />
          </button>
          {isGeneratedImage && (
            <a
              href={safeFullImageUrl}
              download="areqa-image.png"
              target="_blank"
              rel="noopener noreferrer"
              aria-label={language === 'en' ? 'Download image' : '下載圖片'}
              title={language === 'en' ? 'Download image' : '下載圖片'}
              className={`${styles.answerImageLightboxClose} ${styles.answerImageLightboxDownload}`}
              onClick={handleGeneratedDownload}
            >
              <Download size={20} aria-hidden="true" />
            </a>
          )}
          <button
            type="button"
            className={styles.answerImageLightboxClose}
            aria-label="關閉圖片檢視"
            onClick={() => setIsLightboxOpen(false)}
          >
            <X size={20} aria-hidden="true" />
          </button>
          <div className={styles.answerImageLightboxStage} onClick={(event) => event.stopPropagation()}>
            {safeSourceUrl && !isPdfAttachmentImage && !isGeneratedImage ? (
              <a
                href={safeSourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.answerImageLightboxImageLink}
                title={block.sourceUrl}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={safeFullImageUrl}
                  alt={displayCaption}
                  className={styles.answerImageLightboxImage}
                />
              </a>
            ) : (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={safeFullImageUrl}
                alt={displayCaption}
                className={styles.answerImageLightboxImage}
              />
            )}
          </div>
          {!isGeneratedImage && <div className={styles.answerImageLightboxMeta} onClick={(event) => event.stopPropagation()}>
            {!isGeneratedImage && <p className={styles.answerImageLightboxCaption}>{displayCaption}</p>}
            {displayExplanatoryCaption && <p>{displayExplanatoryCaption}</p>}
            {(block.attributionString || block.creator) && (
              <p>{block.attributionString || block.creator}</p>
            )}
            <div className={styles.answerImageLightboxSourceLine}>
              <span>{sourceLabel}</span>
              {isPdfAttachmentImage ? (
                <span>{t('uploadedAttachmentBadge')}</span>
              ) : isGeneratedImage ? null : safeSourceUrl ? (
                <a
                  href={safeSourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.answerImageLightboxSource}
                  title={block.sourceUrl}
                >
                  開啟原始來源
                  <ExternalLink size={14} aria-hidden="true" />
                </a>
              ) : null}
            </div>
          </div>}
        </div>
        ,
        document.body
      )}
    </>
  );
}

/**
 * Render structured illustrated answer blocks in backend-provided order.
 */
function AnswerBlocksRenderer({
  blocks,
  conversationId,
  markdownComponents,
  styles,
}: {
  blocks: AnswerBlock[];
  conversationId: string;
  markdownComponents: Components;
  styles: ReturnType<typeof useStyles>['styles'];
}) {
  return (
    <>
      {blocks.map((block, index) => {
        if (block.type === 'image_block') {
          return (
            <div
              data-answer-block-index={index}
              key={block.slotId || `image-${index}`}
            >
              <ImageBlockCard block={block} conversationId={conversationId} styles={styles} />
            </div>
          );
        }

        return (
          <div
            data-answer-block-index={index}
            key={`paragraph-${index}`}
          >
            <StreamingMarkdown
              content={block.text}
              markdownComponents={markdownComponents}
            />
          </div>
        );
      })}
    </>
  );
}

type LiveAnswerPart =
  | { type: 'text'; key: string; text: string }
  | { type: 'image_slot'; key: string; slot: StreamingImageSlot };

/**
 * Build stable live-render parts around backend-authorized image offsets.
 *
 * Args:
 *   content: Public marker-free answer text.
 *   slots: Privacy-safe marker positions from the SSE stream.
 *
 * Returns:
 *   Text and image-slot parts with keys that remain stable as later slots arrive.
 */
function buildLiveAnswerParts(content: string, slots: StreamingImageSlot[]): LiveAnswerPart[] {
  const orderedSlots = [...slots].sort((left, right) =>
    left.contentOffset - right.contentOffset || left.slotId.localeCompare(right.slotId)
  );
  const parts: LiveAnswerPart[] = [];
  let cursor = 0;
  let textKey = 'live-text-start';

  for (const slot of orderedSlots) {
    const offset = Math.min(Math.max(slot.contentOffset, cursor), content.length);
    parts.push({ type: 'text', key: textKey, text: content.slice(cursor, offset) });
    parts.push({ type: 'image_slot', key: `live-image-${slot.slotId}`, slot });
    cursor = offset;
    textKey = `live-text-after-${slot.slotId}`;
  }
  parts.push({ type: 'text', key: textKey, text: content.slice(cursor) });
  return parts;
}

/** Create a display-only skeleton while the final verified block is pending. */
function pendingImageBlock(slot: StreamingImageSlot): ImageBlock {
  return {
    type: 'image_block',
    slotId: slot.slotId,
    topic: 'Visual aid',
    purpose: 'diagram',
    imageUrl: '',
    sourceUrl: '',
    sourceDomain: '',
    caption: '正在尋找合適圖片',
    status: 'pending',
    safetyStatus: 'unavailable',
    matchConfidence: 0,
  };
}

/**
 * Render the live answer without replacing already-mounted Markdown nodes.
 *
 * Final image metadata resolves the existing slot in place. Text continues to
 * use the original public Markdown, while historical messages remain backed by
 * persisted ``answerBlocks`` for deterministic reloads.
 */
function LiveOrderedAnswerRenderer({
  content,
  slots,
  blocks,
  conversationId,
  markdownComponents,
  styles,
  isStreaming,
}: {
  content: string;
  slots: StreamingImageSlot[];
  blocks: AnswerBlock[];
  conversationId: string;
  markdownComponents: Components;
  styles: ReturnType<typeof useStyles>['styles'];
  isStreaming: boolean;
}) {
  const parts = React.useMemo(() => buildLiveAnswerParts(content, slots), [content, slots]);
  const imageBlocks = React.useMemo(
    () => new Map(
      blocks
        .filter((block): block is ImageBlock => block.type === 'image_block')
        .map((block) => [block.slotId, block]),
    ),
    [blocks],
  );
  return (
    <>
      {parts.map((part) => {
        if (part.type === 'text') {
          if (!part.text) return null;
          return (
            <div data-live-answer-part={part.key} key={part.key}>
              <StreamingMarkdown
                content={part.text}
                markdownComponents={markdownComponents}
              />
            </div>
          );
        }

        const imageBlock = imageBlocks.get(part.slot.slotId);
        if (!imageBlock && !isStreaming) return null;
        return (
          <div
            data-live-answer-part={part.key}
            key={part.key}
          >
            <ImageBlockCard block={imageBlock ?? pendingImageBlock(part.slot)} conversationId={conversationId} styles={styles} />
          </div>
        );
      })}
    </>
  );
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
  onDeleteLatestTurn,
  onAddNote,
  isSavedNote = false,
  onEdit,
  onFeedback,
  isLast = false,
  onSelectSuggestion,
  className,
}: MessageItemProps) {
  const { styles, cx } = useStyles();
  const { message: antMessageApi } = App.useApp();
  const { t } = useUserPreferences();
  const isUser = message.role === 'user';
  const hasLiveStreamed = useHasLiveStreamed(isStreaming && !thinking?.isThinking);
  const legacyMessage = React.useMemo(
    () => splitLegacyAttachmentMarker(message.content),
    [message.content],
  );
  const displayContent = isUser ? legacyMessage.content : message.content;
  const hasAnswerBlocks = Boolean(message.answerBlocks && message.answerBlocks.length > 0);
  const isImageGenerationPending = Boolean(message.answerBlocks?.some((block) => (
    block.type === 'image_block' && block.provider === 'generated_image' && block.status === 'pending'
  )));
  const liveImageSlots = message.streamImageSlots ?? [];
  const answerBlockImageCount = React.useMemo(
    () => (message.answerBlocks ?? []).filter((block) => block.type === 'image_block').length,
    [message.answerBlocks],
  );
  const hasCompleteLiveImageSlots =
    !hasAnswerBlocks || answerBlockImageCount === 0 || liveImageSlots.length >= answerBlockImageCount;
  const hasActiveVoiceCaption = Boolean(message.voicePlayback && message.voicePlayback !== 'finished');
  const shouldUseLiveOrderedAnswer =
    !hasActiveVoiceCaption && hasLiveStreamed && liveImageSlots.length > 0 && (isStreaming || hasCompleteLiveImageSlots);
  const shouldUseStructuredAnswerBlocks = !hasActiveVoiceCaption && hasAnswerBlocks && !shouldUseLiveOrderedAnswer;
  const generatedImageStatusContent = shouldUseStructuredAnswerBlocks
    && message.answerBlocks?.every((block) => block.type === 'image_block' && block.provider === 'generated_image')
    && !LEGACY_IMAGE_COMPLETION_TEXT.has(message.content.trim())
    && !message.answerBlocks.some((block) => block.type === 'image_block' && block.caption === message.content)
    ? message.content : '';
  const displayAttachments = React.useMemo(() => {
    if (message.attachments && message.attachments.length > 0) return message.attachments;
    return createLegacyAttachmentMetadata(legacyMessage.legacyCount);
  }, [legacyMessage.legacyCount, message.attachments]);
  const isLiked = message.feedback === 'liked';
  const isDisliked = message.feedback === 'disliked';
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [isMobileFeedbackModal, setIsMobileFeedbackModal] = useState(false);
  const [feedbackReason, setFeedbackReason] = useState<MessageFeedbackReason | null>(
    message.feedbackReason ?? null,
  );
  const [feedbackComment, setFeedbackComment] = useState(message.feedbackComment ?? '');
  const [isFeedbackSubmitting, setIsFeedbackSubmitting] = useState(false);
  const [bubbleEl, setBubbleEl] = useState<HTMLDivElement | null>(null);
  const [areAttachmentsExpanded, setAreAttachmentsExpanded] = useState(false);
  const [isReadAloudLoading, setIsReadAloudLoading] = useState(false);
  const [isReadAloudPlaying, setIsReadAloudPlaying] = useState(false);
  const readAloudAudioRef = React.useRef<HTMLAudioElement | null>(null);
  const readAloudObjectUrlRef = React.useRef<string | null>(null);
  const readAloudAbortRef = React.useRef<AbortController | null>(null);
  const setBubbleRef = useCallback((node: HTMLDivElement | null) => {
    setBubbleEl(node);
  }, []);

  React.useEffect(() => {
    setFeedbackReason(message.feedbackReason ?? null);
    setFeedbackComment(message.feedbackComment ?? '');
  }, [message.feedbackComment, message.feedbackReason]);

  React.useEffect(() => {
    return () => {
      readAloudAbortRef.current?.abort();
      readAloudAudioRef.current?.pause();
      if (readAloudObjectUrlRef.current) {
        URL.revokeObjectURL(readAloudObjectUrlRef.current);
      }
    };
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

  const handleCopyMath = useCallback(async (latex: string) => {
    try {
      await navigator.clipboard.writeText(latex);
      antMessageApi.success(t('copyFormulaSuccess'));
    } catch {
      antMessageApi.error(t('copyFormulaFailed'));
    }
  }, [antMessageApi, t]);

  const handleCopyTable = useCallback(async (tableText: string) => {
    if (!tableText.trim()) {
      antMessageApi.error?.('複製表格失敗');
      return;
    }

    try {
      await navigator.clipboard.writeText(tableText);
      antMessageApi.success?.('已複製表格');
    } catch {
      antMessageApi.error?.('複製表格失敗');
    }
  }, [antMessageApi]);

  const handleDownloadTable = useCallback((csvText: string) => {
    if (!csvText.trim()) {
      antMessageApi.error?.('下載表格失敗');
      return;
    }

    try {
      downloadCsvFile(csvText, 'areqa-table.csv');
      antMessageApi.success?.('已下載 CSV');
    } catch {
      antMessageApi.error?.('下載表格失敗');
    }
  }, [antMessageApi]);

  const markdownComponents = React.useMemo(
    () => createMarkdownComponents(
      message.id,
      !isUser,
      handleCopyMath,
      handleCopyTable,
      handleDownloadTable,
      {
        actions: t('tableActions'),
        copy: t('copyTable'),
        downloadCsv: t('downloadTableCsv'),
        expand: t('expandTable'),
        scrollable: t('scrollableTable'),
        title: t('table'),
        close: t('closeExpandedTable'),
      },
      t('copyFormula'),
      styles.content,
    ),
    [handleCopyMath, handleCopyTable, handleDownloadTable, isUser, message.id, styles.content, t]
  );

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(displayContent);
  const [isEditSaving, setIsEditSaving] = useState(false);
  const editTextareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  React.useEffect(() => {
    if (!isEditing) {
      setEditContent(displayContent);
    }
  }, [displayContent, isEditing]);

  React.useEffect(() => {
    const textarea = editTextareaRef.current;
    if (!textarea || !isEditing) return;

    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [editContent, isEditing]);

  // Handle copy message content
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(displayContent);
      antMessageApi.success(t('copyMessageSuccess'));
    } catch {
      antMessageApi.error(t('copyMessageFailed'));
    }
  }, [displayContent, antMessageApi, t]);

  const stopReadAloud = useCallback(() => {
    readAloudAbortRef.current?.abort();
    readAloudAbortRef.current = null;
    readAloudAudioRef.current?.pause();
    readAloudAudioRef.current = null;
    if (readAloudObjectUrlRef.current) {
      URL.revokeObjectURL(readAloudObjectUrlRef.current);
      readAloudObjectUrlRef.current = null;
    }
    setIsReadAloudPlaying(false);
    setIsReadAloudLoading(false);
  }, []);

  const handleReadAloud = useCallback(async () => {
    if (isReadAloudPlaying || isReadAloudLoading) {
      stopReadAloud();
      return;
    }

    const readableText = prepareReadAloudText(message.content);
    if (!readableText) {
      antMessageApi.error(t('readAloudFailed'));
      return;
    }

    setIsReadAloudLoading(true);
    const abortController = new AbortController();
    readAloudAbortRef.current = abortController;
    try {
      const audioBlob = await createReadAloudAudio(readableText, abortController.signal);
      if (abortController.signal.aborted || readAloudAbortRef.current !== abortController) {
        return;
      }
      const objectUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(objectUrl);
      readAloudAudioRef.current = audio;
      readAloudObjectUrlRef.current = objectUrl;

      audio.addEventListener('ended', stopReadAloud, { once: true });
      audio.addEventListener('error', stopReadAloud, { once: true });
      await audio.play();
      setIsReadAloudPlaying(true);
      antMessageApi.info(t('readAloudStarted'));
    } catch {
      if (abortController.signal.aborted) {
        return;
      }
      stopReadAloud();
      antMessageApi.error(t('readAloudFailed'));
    } finally {
      if (readAloudAbortRef.current === abortController) {
        readAloudAbortRef.current = null;
        setIsReadAloudLoading(false);
      }
    }
  }, [antMessageApi, isReadAloudLoading, isReadAloudPlaying, message.content, stopReadAloud, t]);

  // Handle regenerate
  const handleRegenerate = useCallback(() => {
    if (onRegenerate) {
      onRegenerate(message.id);
    }
  }, [onRegenerate, message.id]);

  const handleDeleteLatestTurn = useCallback(() => {
    onDeleteLatestTurn?.(message.id);
  }, [message.id, onDeleteLatestTurn]);

  const handleAddNote = useCallback(() => {
    if (isSavedNote) return;
    onAddNote?.(message.id);
  }, [isSavedNote, message.id, onAddNote]);

  const handleFeedback = useCallback(async (
    feedback: MessageFeedback,
    details: MessageFeedbackDetails = {},
  ) => {
    if (!onFeedback) return;
    if (message.feedback === feedback) return;

    try {
      await onFeedback(message.id, feedback, details);
    } catch {
      antMessageApi.error(t('saveFeedbackFailed'));
    }
  }, [antMessageApi, message.feedback, message.id, onFeedback, t]);

  const handleLikeFeedback = useCallback(async () => {
    if (!onFeedback || isLiked) return;

    await handleFeedback('liked');
    antMessageApi.success(t('feedbackThanks'));
  }, [antMessageApi, handleFeedback, isLiked, onFeedback, t]);

  const openDislikeFeedback = useCallback(() => {
    if (!onFeedback || isLiked || isDisliked) return;

    setFeedbackReason(message.feedbackReason ?? null);
    setFeedbackComment(message.feedbackComment ?? '');
    setIsMobileFeedbackModal(isMobileFeedbackViewport());
    setIsFeedbackModalOpen(true);
  }, [isDisliked, isLiked, message.feedbackComment, message.feedbackReason, onFeedback]);

  const closeDislikeFeedback = useCallback(() => {
    if (isFeedbackSubmitting) return;

    setIsFeedbackModalOpen(false);
  }, [isFeedbackSubmitting]);

  const submitDislikeFeedback = useCallback(async () => {
    if (!onFeedback || !feedbackReason) return;

    setIsFeedbackSubmitting(true);
    try {
      await onFeedback(message.id, 'disliked', {
        reason: feedbackReason,
        comment: feedbackComment.trim() || null,
      });
      setIsFeedbackModalOpen(false);
      window.setTimeout(() => {
        antMessageApi.success(t('feedbackThanks'));
      }, 0);
    } catch {
      antMessageApi.error(t('saveFeedbackFailed'));
    } finally {
      setIsFeedbackSubmitting(false);
    }
  }, [antMessageApi, feedbackComment, feedbackReason, message.id, onFeedback, t]);

  // Handle entering edit mode
  const handleEditClick = useCallback(() => {
    setEditContent(displayContent);
    setIsEditing(true);
  }, [displayContent]);

  // Handle canceling edit
  const handleCancelEdit = useCallback(() => {
    if (isEditSaving) return;
    setIsEditing(false);
    setEditContent(displayContent);
  }, [displayContent, isEditSaving]);

  // Handle saving edit
  const handleSaveEdit = useCallback(async () => {
    const trimmedContent = editContent.trim();
    if (!trimmedContent || isEditSaving) return;
    if (trimmedContent === displayContent || !onEdit) {
      setIsEditing(false);
      return;
    }

    setIsEditSaving(true);
    try {
      const editPromise = Promise.resolve(onEdit(message.id, trimmedContent));
      if (isUser) {
        setIsEditing(false);
        setEditContent(trimmedContent);
        await editPromise;
      } else {
        await editPromise;
        setIsEditing(false);
      }
    } catch {
      // Keep assistant drafts open; user edits close optimistically so the new
      // stream can render in the normal message layout while errors surface via
      // the parent toast.
      if (!isUser) setIsEditing(true);
    } finally {
      setIsEditSaving(false);
    }
  }, [displayContent, editContent, isEditSaving, isUser, message.id, onEdit]);

  // Handle keyboard shortcuts in edit mode
  const handleEditKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement | HTMLDivElement>) => {
    if (e.key === 'Escape') {
      handleCancelEdit();
    } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleSaveEdit();
    }
  }, [handleCancelEdit, handleSaveEdit]);

  const handleEditPaste = useCallback((event: React.ClipboardEvent<HTMLTextAreaElement | HTMLDivElement>) => {
    if (isUser) return;

    const imageFile = Array.from(event.clipboardData.files).find((file) => file.type.startsWith('image/'));
    if (!imageFile) return;

    event.preventDefault();
    if (imageFile.size > MAX_PASTED_IMAGE_BYTES) {
      antMessageApi.error('圖片太大，請貼上 512 KB 以下的圖片');
      return;
    }

    const pasteTarget = event.currentTarget;
    const isTextareaPaste = pasteTarget instanceof HTMLTextAreaElement;
    const selectionStart = isTextareaPaste ? pasteTarget.selectionStart : undefined;
    const selectionEnd = isTextareaPaste ? pasteTarget.selectionEnd : undefined;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== 'string') return;
      const markdownImage = `![${imageFile.name || 'pasted image'}](${reader.result})`;
      setEditContent((current) => {
        if (!isTextareaPaste) {
          const editor = pasteTarget as HTMLElement;
          const fragment = htmlFragmentFromMarkdown(markdownImage);
          const insertedNode = insertFragmentNearSelection(editor, fragment);
          if (insertedNode) placeCaretAtEnd(insertedNode);
          return editorHtmlToMarkdown(editor);
        }

        return insertTextAtSelection(
          current,
          `\n${markdownImage}\n`,
          selectionStart,
          selectionEnd,
        );
      });
    };
    reader.onerror = () => {
      antMessageApi.error('貼上圖片失敗');
    };
    reader.readAsDataURL(imageFile);
  }, [antMessageApi, isUser]);

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
              <div className={cx(styles.bubble, styles.userBubble, styles.userEditBubble)}>
                <textarea
                  aria-label={t('editMessage')}
                  autoFocus
                  className={styles.editTextarea}
                  disabled={isEditSaving}
                  onChange={(e) => setEditContent(e.target.value)}
                  onKeyDown={handleEditKeyDown}
                  placeholder="輸入訊息..."
                  ref={editTextareaRef}
                  rows={editingTextareaRows(editContent)}
                  value={editContent}
                />
              </div>
              {displayAttachments.length > 0 && (
                <div
                  className={styles.messageAttachmentList}
                  aria-label={t('messageAttachments', { count: displayAttachments.length })}
                >
                  {displayAttachments.length === 1 ? (
                    <AttachmentCard attachment={displayAttachments[0]} />
                  ) : (
                    <AttachmentToggleList
                      attachments={displayAttachments}
                      expanded={areAttachmentsExpanded}
                      listId={`message-attachments-edit-${message.id}`}
                      onExpandedChange={setAreAttachmentsExpanded}
                    />
                  )}
                </div>
              )}
              <div className={styles.editButtons}>
                <button
                  className={cx(styles.editButton, styles.editCancelButton)}
                  disabled={isEditSaving}
                  onClick={handleCancelEdit}
                >
                  {t('cancel')}
                </button>
                <button
                  className={cx(styles.editButton, styles.editSaveButton)}
                  onClick={handleSaveEdit}
                  disabled={isEditSaving || !editContent.trim() || editContent.trim() === displayContent}
                >
                  {t('submit')}
                </button>
              </div>
            </div>
          ) : (
            /* Normal Display Mode */
            <div className={cx(styles.bubbleWrapper, 'bubbleWrapper')}>
              {(() => {
                // Split content into citation and the rest
                // Pattern matches one or more lines starting with '>' at the beginning
                const quoteMatch = displayContent.match(/^((?:>[^\n]*(?:\n|$))+)\n*([\s\S]*)$/);
                
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
                              remarkPlugins={[remarkGfm, remarkMath]}
                              rehypePlugins={[[rehypeKatex, { throwOnError: false }], rehypeMathSource]}
                              components={markdownComponents}
                              disallowedElements={['script', 'iframe', 'object', 'embed']}
                            >
                              {normalizeMessageMarkdown(remainingText)}
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
                    {displayContent && <div className={styles.content}>
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[[rehypeKatex, { throwOnError: false }], rehypeMathSource]}
                        components={markdownComponents}
                        disallowedElements={['script', 'iframe', 'object', 'embed']}
                      >
                        {normalizeMessageMarkdown(displayContent)}
                      </ReactMarkdown>
                    </div>}
                  </div>
                );
              })()}

              {displayAttachments.length > 0 && (
                <div
                  className={styles.messageAttachmentList}
                  aria-label={t('messageAttachments', { count: displayAttachments.length })}
                >
                  {displayAttachments.length === 1 ? (
                    <AttachmentCard attachment={displayAttachments[0]} />
                  ) : (
                    <AttachmentToggleList
                      attachments={displayAttachments}
                      expanded={areAttachmentsExpanded}
                      listId={`message-attachments-${message.id}`}
                      onExpandedChange={setAreAttachmentsExpanded}
                    />
                  )}
                </div>
              )}
              
              <div className={styles.userActionButtons}>
                <Tooltip title={t('copyMessage')}>
                  <button
                    className={styles.actionButton}
                    onClick={handleCopy}
                    aria-label={t('copyMessage')}
                  >
                    <Copy size={16} />
                  </button>
                </Tooltip>
                {onEdit && (
                  <Tooltip title={t('editMessage')}>
                    <button
                      className={styles.actionButton}
                      onClick={handleEditClick}
                      aria-label={t('editMessage')}
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
            {/* RAG Status Panel - Should be at the top and only visible before thinking or content starts */}
            {!isImageGenerationPending && ragInfo && ragInfo.status !== 'idle' && ragInfo.status !== 'done' && !thinking?.isThinking && !thinking?.content && !message.content && (
              <RAGStatusPanel ragInfo={ragInfo} />
            )}

            {/* Thinking Panel */}
            {thinking?.isThinking && (
              <div className={styles.thinkingPanelWrapper}>
                <ThinkingPanel
                  content={thinking.content}
                  duration={thinking.duration}
                  isThinking={thinking?.isThinking}
                  defaultExpanded={thinking?.isThinking}
                />
              </div>
            )}

            {isEditing ? (
              <div className={styles.editModeContainer}>
                <div className={cx(styles.bubble, styles.assistantBubble, styles.assistantEditSurface)}>
                  <AssistantRichMarkdownEditor
                    className={styles.richEditSurface}
                    disabled={isEditSaving}
                    label={t('editMessage')}
                    menuClassName={styles.richEditSlashMenu}
                    menuItemClassName={styles.richEditSlashMenuItem}
                    onChange={setEditContent}
                    onKeyDown={handleEditKeyDown}
                    onPaste={handleEditPaste}
                    value={editContent}
                  />
                </div>
                <div className={styles.editButtons}>
                  <button
                    className={cx(styles.editButton, styles.editCancelButton)}
                    disabled={isEditSaving}
                    onClick={handleCancelEdit}
                    type="button"
                  >
                    {t('cancel')}
                  </button>
                  <button
                    className={cx(styles.editButton, styles.editSaveButton)}
                    disabled={isEditSaving || !editContent.trim() || editContent.trim() === displayContent}
                    onClick={handleSaveEdit}
                    type="button"
                  >
                    {t('save')}
                  </button>
                </div>
              </div>
            ) : (
              /* Message Bubble */
              <div 
                ref={setBubbleRef}
                className={cx(styles.bubble, styles.assistantBubble, styles.assistantBubbleReveal)}
                data-role="assistant-bubble"
              >
                {/* Message Content */}
                <div
                  className={cx(styles.content, isStreaming && !thinking?.isThinking && styles.streamingContentReveal)}
                  data-streaming-content={isStreaming && !thinking?.isThinking ? 'true' : undefined}
                >
                  {generatedImageStatusContent && <StreamingMarkdown content={generatedImageStatusContent} markdownComponents={markdownComponents} />}
                  {shouldUseLiveOrderedAnswer ? (
                    <LiveOrderedAnswerRenderer
                      conversationId={message.conversationId}
                      content={message.content}
                      slots={liveImageSlots}
                      blocks={message.answerBlocks ?? []}
                      markdownComponents={markdownComponents}
                      styles={styles}
                      isStreaming={isStreaming && !thinking?.isThinking}
                    />
                  ) : shouldUseStructuredAnswerBlocks ? (
                    <AnswerBlocksRenderer
                      conversationId={message.conversationId}
                      blocks={message.answerBlocks ?? []}
                      markdownComponents={markdownComponents}
                      styles={styles}
                    />
                  ) : (
                    <StreamingMarkdown
                      content={message.content}
                      animate={(isStreaming && hasLiveStreamed) || message.voicePlayback === 'waiting' || message.voicePlayback === 'playing'}
                      voicePlayback={message.voicePlayback}
                      voiceCaption={message.voiceCaption}
                      markdownComponents={markdownComponents}
                    />
                  )}
                  {isStreaming && !thinking?.isThinking && (
                    <span className={styles.streamingDots} aria-hidden="true">
                      <span className={styles.streamingDot} />
                      <span className={styles.streamingDot} />
                      <span className={styles.streamingDot} />
                    </span>
                  )}
                </div>

                {/* Citations / Sources Panel */}
                {((message.sources && message.sources.length > 0) || 
                  (ragInfo?.sources && ragInfo.sources.length > 0) || 
                  (message.citations && message.citations.length > 0)) && (
                  <div className={cx(styles.citationsWrapper, styles.citationsReveal)}>
                    <Citations 
                      messageId={message.id}
                      citations={message.citations || []} 
                      sources={message.sources || ragInfo?.sources}
                    />
                  </div>
                )}

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

            {/* Action Buttons */}
            <div className={styles.actionButtons}>
              <Tooltip title={t('copyMessage')}>
                <button
                  className={styles.actionButton}
                  onClick={handleCopy}
                  aria-label={t('copyMessage')}
                >
                  <Copy size={16} />
                </button>
              </Tooltip>
              {!isStreaming && (
                <Tooltip title={isReadAloudPlaying || isReadAloudLoading ? t('stopReadAloud') : t('readAloud')}>
                  <button
                    className={cx(
                      styles.actionButton,
                      (isReadAloudPlaying || isReadAloudLoading) && styles.actionButtonActive,
                    )}
                    onClick={handleReadAloud}
                    aria-label={isReadAloudPlaying || isReadAloudLoading ? t('stopReadAloud') : t('readAloud')}
                    aria-pressed={isReadAloudPlaying || isReadAloudLoading}
                  >
                    {isReadAloudPlaying || isReadAloudLoading ? (
                      <VolumeX size={16} />
                    ) : (
                      <Volume2 size={16} />
                    )}
                  </button>
                </Tooltip>
              )}
              {(onAddNote || isSavedNote) && !isStreaming && (
                <Tooltip title={isSavedNote ? t('savedToNotes') : t('addToNotes')}>
                  <button
                    className={cx(styles.actionButton, isSavedNote && styles.actionButtonActive)}
                    disabled={isSavedNote}
                    onClick={handleAddNote}
                    aria-label={isSavedNote ? t('savedToNotes') : t('addToNotes')}
                  >
                    <NotebookPen size={16} />
                  </button>
                </Tooltip>
              )}
              {onEdit && !isStreaming && !isImageGenerationPending && (
                <Tooltip title={t('editMessage')}>
                  <button
                    aria-label={t('editMessage')}
                    className={styles.actionButton}
                    onClick={handleEditClick}
                    type="button"
                  >
                    <Edit size={16} />
                  </button>
                </Tooltip>
              )}
              {!isStreaming && onFeedback && (
                <>
                  <span
                    aria-hidden={isDisliked}
                    className={cx(
                      styles.feedbackActionSlot,
                      isDisliked && styles.feedbackActionSlotCollapsed,
                    )}
                  >
                    <Tooltip title={t('helpfulReply')}>
                      <button
                        className={cx(
                          styles.actionButton,
                          isLiked && styles.actionButtonActive,
                        )}
                        disabled={isDisliked}
                        onClick={handleLikeFeedback}
                        aria-label={t('helpfulReply')}
                        aria-pressed={isLiked}
                        tabIndex={isDisliked ? -1 : undefined}
                      >
                        <ThumbsUp fill={isLiked ? 'currentColor' : 'none'} size={16} />
                      </button>
                    </Tooltip>
                  </span>
                  <span
                    aria-hidden={isLiked}
                    className={cx(
                      styles.feedbackActionSlot,
                      isLiked && styles.feedbackActionSlotCollapsed,
                    )}
                  >
                    <Tooltip title={t('notHelpfulReply')}>
                      <button
                        className={cx(
                          styles.actionButton,
                          isDisliked && styles.actionButtonActive,
                        )}
                        disabled={isLiked}
                        onClick={openDislikeFeedback}
                        aria-label={t('notHelpfulReply')}
                        aria-pressed={isDisliked}
                        tabIndex={isLiked ? -1 : undefined}
                      >
                        <ThumbsDown fill={isDisliked ? 'currentColor' : 'none'} size={16} />
                      </button>
                    </Tooltip>
                  </span>
                </>
              )}
              {onRegenerate && !isStreaming && !isImageGenerationPending && (
                <Tooltip title={t('regenerate')}>
                  <button
                    className={styles.actionButton}
                    onClick={handleRegenerate}
                    aria-label={t('regenerateMessage')}
                  >
                    <RefreshCw size={16} />
                  </button>
                </Tooltip>
              )}
              {onDeleteLatestTurn && !isStreaming && !isImageGenerationPending && (
                <Tooltip title={t('deleteLatestConversationTurn')}>
                  <button
                    className={styles.actionButton}
                    onClick={handleDeleteLatestTurn}
                    aria-label={t('deleteLatestConversationTurn')}
                  >
                    <Trash2 size={16} />
                  </button>
                </Tooltip>
              )}
            </div>
            {onFeedback && (
              <Modal
                centered={!isMobileFeedbackModal}
                className={cx(
                  styles.feedbackModal,
                  isMobileFeedbackModal && styles.feedbackSheetModal,
                )}
                closable={!isMobileFeedbackModal}
                footer={null}
                maskClosable={!isFeedbackSubmitting}
                onCancel={closeDislikeFeedback}
                open={isFeedbackModalOpen}
                title={null}
                wrapClassName={isMobileFeedbackModal ? styles.feedbackSheetWrap : undefined}
              >
                <div className={styles.feedbackForm}>
                  {isMobileFeedbackModal && <div className={styles.feedbackSheetHandle} />}
                  <div className={styles.feedbackTitle}>{t('feedbackTitleShort')}</div>

                  <div className={styles.mobileFeedbackReason}>
                    <div className={styles.feedbackLabel}>{t('feedbackIssue')}</div>
                    <select
                      aria-label={t('selectIssue')}
                      className={styles.mobileFeedbackNativeSelect}
                      onChange={(event) => setFeedbackReason(event.target.value as MessageFeedbackReason)}
                      value={feedbackReason ?? ''}
                    >
                      <option disabled value="">{t('selectIssue')}</option>
                      {FEEDBACK_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {t(option.labelKey)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className={styles.desktopFeedbackReasons}>
                    {FEEDBACK_OPTIONS.map((option) => (
                      <button
                        className={cx(
                          styles.feedbackReasonChip,
                          feedbackReason === option.value && styles.feedbackReasonChipSelected,
                        )}
                        key={option.value}
                        onClick={() => setFeedbackReason(option.value)}
                        type="button"
                      >
                        {t(option.labelKey)}
                      </button>
                    ))}
                  </div>

                  <TextArea
                    className={styles.feedbackTextArea}
                    maxLength={2000}
                    onChange={(event) => setFeedbackComment(event.target.value)}
                    placeholder={t('feedbackDetailsPlaceholder')}
                    rows={isMobileFeedbackModal ? 8 : 4}
                    value={feedbackComment}
                  />

                  <div className={styles.feedbackPrivacyText}>
                    {t('feedbackPrivacy')}
                  </div>

                  <div className={styles.feedbackSubmitRow}>
                    <Button
                      className={styles.feedbackSubmitButton}
                      disabled={!feedbackReason}
                      loading={isFeedbackSubmitting}
                      onClick={submitDislikeFeedback}
                      type="primary"
                    >
                      {t('feedbackSubmit')}
                    </Button>
                  </div>
                </div>
              </Modal>
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default MessageItem;
