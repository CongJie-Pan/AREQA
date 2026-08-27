'use client';

/**
 * MessageItem Component
 * Displays a single message in the conversation
 */

import React, { memo, useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown, { Components } from 'react-markdown';
import { Streamdown, type Components as StreamdownComponents } from 'streamdown';
import { createMathPlugin } from '@streamdown/math';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Copy, Download, Maximize2, RefreshCw, Edit, CornerDownRight, ThumbsDown, ThumbsUp, ExternalLink, X } from 'lucide-react';
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
import { normalizeDisplayMathBlocks, rehypeMathSource } from '@/utils/markdownMath';
import { AttachmentCard } from './AttachmentCard';
import { AttachmentToggleList } from './AttachmentToggleList';
import { createLegacyAttachmentMetadata, splitLegacyAttachmentMarker } from '@/utils/attachments';
import { useUserPreferences, type InterfaceLanguage, type TranslationKey } from '@/contexts/UserPreferencesContext';

const { TextArea } = Input;
const STREAMING_MARKDOWN_FLUSH_MS = 56;
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
            e.currentTarget.style.backgroundColor = 'rgba(212, 175, 55, 0.3)';
            e.currentTarget.style.borderColor = 'rgba(212, 175, 55, 0.6)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(212, 175, 55, 0.15)';
            e.currentTarget.style.borderColor = 'rgba(212, 175, 55, 0.3)';
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
            color: '#d4af37',
            backgroundColor: 'rgba(212, 175, 55, 0.15)',
            border: '1px solid rgba(212, 175, 55, 0.3)',
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
  /** Callback when edit is submitted (user messages only) */
  onEdit?: (messageId: string, newContent: string) => void;
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
}: {
  content: string;
  markdownComponents: Components;
}) {
  const throttledContent = useThrottledValue(content, STREAMING_MARKDOWN_FLUSH_MS);
  const deferredContent = React.useDeferredValue(throttledContent);
  const processedContent = React.useMemo(() => {
    return normalizeDisplayMathBlocks(normalizeCitationMarkers(deferredContent));
  }, [deferredContent]);

  return (
    <Streamdown
      components={markdownComponents as StreamdownComponents}
      controls={false}
      disallowedElements={['script', 'iframe', 'object', 'embed']}
      linkSafety={STREAMDOWN_LINK_SAFETY}
      mode="streaming"
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
 * source attribution visible and rejects unsafe URLs before they reach the DOM.
 */
function ImageBlockCard({ block, styles }: { block: ImageBlock; styles: ReturnType<typeof useStyles>['styles'] }) {
  const { language, t } = useUserPreferences();
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);
  const [isImageLoaded, setIsImageLoaded] = useState(false);
  const isPdfAttachmentImage = block.provider === 'pdf_attachment';
  const imageUrl = normalizeSupabaseStorageImageUrl(block.thumbnailUrl || block.imageUrl);
  const fullImageUrl = normalizeSupabaseStorageImageUrl(block.imageUrl || block.thumbnailUrl);
  const safeImageUrl = isSafeImageUrl(imageUrl) ? imageUrl : '';
  const safeFullImageUrl = isSafeImageUrl(fullImageUrl) ? fullImageUrl : safeImageUrl;
  const safeSourceUrl = isSafeUrl(block.sourceUrl) ? block.sourceUrl : '';
  const rawDisplayCaption = block.attributionCaption || block.caption || block.topic;
  const displayCaption = isPdfAttachmentImage
    ? localizePdfAttachmentCaption(rawDisplayCaption, language, t)
    : rawDisplayCaption;
  const sourceLabel = isPdfAttachmentImage ? t('pdfAttachmentSource') : block.sourceDomain || 'source';
  const visualStatus = block.status || (block.imageUrl ? 'resolved' : 'pending');
  const imageFrameStyle = getImageAspectRatio(block);

  React.useEffect(() => {
    setIsImageLoaded(false);
  }, [safeImageUrl]);

  if (visualStatus === 'pending') {
    return (
      <figure className={styles.answerImageCard} aria-label="圖片載入中">
        <div
          className={styles.answerImagePendingFrame}
          role="status"
          aria-label="圖片搜尋中"
          style={imageFrameStyle}
        >
          <div className={styles.answerImageSkeleton} data-testid="answer-image-skeleton" />
          <span className={styles.answerImagePendingLabel}>{displayCaption}</span>
        </div>
      </figure>
    );
  }

  if (!safeImageUrl || (!safeSourceUrl && !isPdfAttachmentImage) || block.safetyStatus !== 'pass') {
    return null;
  }

  return (
    <>
      {block.explanatoryCaption && (
        <p className={styles.answerImageExplanation}>{block.explanatoryCaption}</p>
      )}
      <figure className={styles.answerImageCard}>
        <button
          type="button"
          className={styles.answerImageButton}
          style={imageFrameStyle}
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
            src={safeImageUrl}
            alt={displayCaption}
            className={`${styles.answerImage} ${isImageLoaded ? styles.answerImageLoaded : ''}`}
            loading="lazy"
            onLoad={() => setIsImageLoaded(true)}
          />
        </button>
        <figcaption className={`${styles.answerImageCaption} ${isImageLoaded ? styles.answerImageCaptionVisible : ''}`}>
          <span className={styles.answerImageCaptionText}>{displayCaption}</span>
          <span className={styles.answerImageMetaLine}>
            <span>{sourceLabel}</span>
            {isPdfAttachmentImage ? (
              <span>{t('uploadedAttachmentBadge')}</span>
            ) : (
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
        </figcaption>
      </figure>
      <Modal
        open={isLightboxOpen}
        onCancel={() => setIsLightboxOpen(false)}
        footer={null}
        centered
        width="min(92vw, 1080px)"
        className={styles.answerImageLightbox}
        title={displayCaption}
      >
        <div className={styles.answerImageLightboxBody}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={safeFullImageUrl}
            alt={displayCaption}
            className={styles.answerImageLightboxImage}
          />
          <div className={styles.answerImageLightboxMeta}>
            {block.explanatoryCaption && <p>{block.explanatoryCaption}</p>}
            {(block.attributionString || block.creator) && (
              <p>
                <strong>Attribution:</strong> {block.attributionString || block.creator}
              </p>
            )}
            {!isPdfAttachmentImage && safeSourceUrl && (
              <a
                href={safeSourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.answerImageLightboxSource}
              >
                View original source
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            )}
          </div>
        </div>
      </Modal>
    </>
  );
}

/**
 * Render structured illustrated answer blocks in backend-provided order.
 */
function AnswerBlocksRenderer({
  blocks,
  markdownComponents,
  styles,
}: {
  blocks: AnswerBlock[];
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
              <ImageBlockCard block={block} styles={styles} />
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
  markdownComponents,
  styles,
  isStreaming,
}: {
  content: string;
  slots: StreamingImageSlot[];
  blocks: AnswerBlock[];
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
            <ImageBlockCard block={imageBlock ?? pendingImageBlock(part.slot)} styles={styles} />
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
  const liveImageSlots = message.streamImageSlots ?? [];
  const shouldUseLiveOrderedAnswer = hasLiveStreamed && liveImageSlots.length > 0;
  const shouldUseStructuredAnswerBlocks = hasAnswerBlocks && !shouldUseLiveOrderedAnswer;
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
  const setBubbleRef = useCallback((node: HTMLDivElement | null) => {
    setBubbleEl(node);
  }, []);

  React.useEffect(() => {
    setFeedbackReason(message.feedbackReason ?? null);
    setFeedbackComment(message.feedbackComment ?? '');
  }, [message.feedbackComment, message.feedbackReason]);

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

  // Handle copy message content
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(displayContent);
      antMessageApi.success(t('copyMessageSuccess'));
    } catch {
      antMessageApi.error(t('copyMessageFailed'));
    }
  }, [displayContent, antMessageApi, t]);

  // Handle regenerate
  const handleRegenerate = useCallback(() => {
    if (onRegenerate) {
      onRegenerate(message.id);
    }
  }, [onRegenerate, message.id]);

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
    setIsEditing(false);
    setEditContent(displayContent);
  }, [displayContent]);

  // Handle saving edit
  const handleSaveEdit = useCallback(() => {
    const trimmedContent = editContent.trim();
    if (trimmedContent && trimmedContent !== displayContent && onEdit) {
      onEdit(message.id, trimmedContent);
    }
    setIsEditing(false);
  }, [displayContent, editContent, message.id, onEdit]);

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
                  {t('cancel')}
                </button>
                <button
                  className={cx(styles.editButton, styles.editSaveButton)}
                  onClick={handleSaveEdit}
                  disabled={!editContent.trim() || editContent.trim() === displayContent}
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
                              {normalizeDisplayMathBlocks(remainingText)}
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
                        {normalizeDisplayMathBlocks(displayContent)}
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
            {ragInfo && ragInfo.status !== 'idle' && ragInfo.status !== 'done' && !thinking?.isThinking && !thinking?.content && !message.content && (
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

            {/* Message Bubble */}
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
                {shouldUseLiveOrderedAnswer ? (
                  <LiveOrderedAnswerRenderer
                    content={message.content}
                    slots={liveImageSlots}
                    blocks={message.answerBlocks ?? []}
                    markdownComponents={markdownComponents}
                    styles={styles}
                    isStreaming={isStreaming && !thinking?.isThinking}
                  />
                ) : shouldUseStructuredAnswerBlocks ? (
                  <AnswerBlocksRenderer
                    blocks={message.answerBlocks ?? []}
                    markdownComponents={markdownComponents}
                    styles={styles}
                  />
                ) : (
                  <StreamingMarkdown
                    content={message.content}
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
              {onRegenerate && !isStreaming && (
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
