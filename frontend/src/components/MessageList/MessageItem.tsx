'use client';

/**
 * MessageItem Component
 * Displays a single message in the conversation
 */

import React, { memo, useCallback, useState } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import { Streamdown, type Components as StreamdownComponents } from 'streamdown';
import { math } from '@streamdown/math';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Copy, RefreshCw, Edit, CornerDownRight, ThumbsDown, ThumbsUp, ExternalLink } from 'lucide-react';
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

const { TextArea } = Input;
const FEEDBACK_SUCCESS_MESSAGE = '感謝你的回饋';
const STREAMING_MARKDOWN_FLUSH_MS = 56;
const STREAMDOWN_PLUGINS = { math };
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

const FEEDBACK_OPTIONS: Array<{ value: MessageFeedbackReason; label: string }> = [
  { value: 'incorrect_or_incomplete', label: '不正確或不完整' },
  { value: 'not_what_i_wanted', label: '這不是我想要的' },
  { value: 'slow_or_broken', label: '緩慢或故障' },
  { value: 'style_or_tone', label: '風格或語調' },
  { value: 'safety_or_legal', label: '安全性或法律疑慮' },
  { value: 'other', label: '其他' },
];

function isMobileFeedbackViewport(): boolean {
  return window.matchMedia('(max-width: 768px)').matches;
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

const createMarkdownComponents = (
  messageId: string,
  enableMathCopy: boolean,
  onCopyMath: (latex: string) => void,
): Components => ({
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
            aria-label="複製 LaTeX 公式"
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
            複製公式
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
  isStreaming,
  hasLiveStreamed,
}: {
  content: string;
  markdownComponents: Components;
  isStreaming?: boolean;
  hasLiveStreamed?: boolean;
}) {
  const throttledContent = useThrottledValue(content, STREAMING_MARKDOWN_FLUSH_MS);
  const deferredContent = React.useDeferredValue(throttledContent);
  const shouldKeepAnimatedDom = useHasLiveStreamed(isStreaming || hasLiveStreamed);
  const processedContent = React.useMemo(() => {
    return normalizeDisplayMathBlocks(normalizeCitationMarkers(deferredContent));
  }, [deferredContent]);

  return (
    <Streamdown
      animated
      components={markdownComponents as StreamdownComponents}
      controls={false}
      disallowedElements={['script', 'iframe', 'object', 'embed']}
      isAnimating={shouldKeepAnimatedDom}
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
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);
  const [isImageLoaded, setIsImageLoaded] = useState(false);
  const imageUrl = block.thumbnailUrl || block.imageUrl;
  const safeImageUrl = isSafeUrl(imageUrl) ? imageUrl : '';
  const safeFullImageUrl = safeImageUrl;
  const safeSourceUrl = isSafeUrl(block.sourceUrl) ? block.sourceUrl : '';
  const safeLicenseUrl = isSafeUrl(block.licenseUrl) ? block.licenseUrl : '';
  const displayCaption = block.attributionCaption || block.caption || block.topic;
  const sourceLabel = block.sourceDomain || 'source';
  const licenseLabel = block.license || (block.provider === 'og_image' ? 'License unknown' : '');
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

  if (!safeImageUrl || !safeSourceUrl || block.safetyStatus !== 'pass') {
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
          aria-label={`放大檢視圖片：${displayCaption}`}
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
            {licenseLabel && <span className={styles.answerImageLicense}>{licenseLabel}</span>}
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
            {licenseLabel && (
              <p>
                <strong>License:</strong>{' '}
                {safeLicenseUrl ? (
                  <a href={safeLicenseUrl} target="_blank" rel="noopener noreferrer">
                    {licenseLabel}
                  </a>
                ) : (
                  licenseLabel
                )}
              </p>
            )}
            <a
              href={safeSourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.answerImageLightboxSource}
            >
              View original source
              <ExternalLink size={14} aria-hidden="true" />
            </a>
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
              isStreaming={false}
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
  hasLiveStreamed,
}: {
  content: string;
  slots: StreamingImageSlot[];
  blocks: AnswerBlock[];
  markdownComponents: Components;
  styles: ReturnType<typeof useStyles>['styles'];
  isStreaming: boolean;
  hasLiveStreamed: boolean;
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
  const lastTextKey = [...parts].reverse().find((part) => part.type === 'text')?.key;

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
                isStreaming={isStreaming && part.key === lastTextKey}
                hasLiveStreamed={hasLiveStreamed}
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
      antMessageApi.success('已複製 LaTeX 公式');
    } catch {
      antMessageApi.error('複製公式失敗');
    }
  }, [antMessageApi]);

  const markdownComponents = React.useMemo(
    () => createMarkdownComponents(message.id, !isUser, handleCopyMath),
    [handleCopyMath, isUser, message.id]
  );

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(displayContent);

  // Handle copy message content
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(displayContent);
      antMessageApi.success('已複製到剪貼簿');
    } catch {
      antMessageApi.error('複製失敗');
    }
  }, [displayContent, antMessageApi]);

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
      antMessageApi.error('儲存評價失敗');
    }
  }, [antMessageApi, message.feedback, message.id, onFeedback]);

  const handleLikeFeedback = useCallback(async () => {
    if (!onFeedback || isLiked) return;

    await handleFeedback('liked');
    antMessageApi.success(FEEDBACK_SUCCESS_MESSAGE);
  }, [antMessageApi, handleFeedback, isLiked, onFeedback]);

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
        antMessageApi.success(FEEDBACK_SUCCESS_MESSAGE);
      }, 0);
    } catch {
      antMessageApi.error('儲存評價失敗');
    } finally {
      setIsFeedbackSubmitting(false);
    }
  }, [antMessageApi, feedbackComment, feedbackReason, message.id, onFeedback]);

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
                  取消
                </button>
                <button
                  className={cx(styles.editButton, styles.editSaveButton)}
                  onClick={handleSaveEdit}
                  disabled={!editContent.trim() || editContent.trim() === displayContent}
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
                <div className={styles.messageAttachmentList} aria-label="訊息附件">
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
              <div className={cx(styles.content, isStreaming && !thinking?.isThinking && styles.streamingContentReveal)}>
                {shouldUseLiveOrderedAnswer ? (
                  <LiveOrderedAnswerRenderer
                    content={message.content}
                    slots={liveImageSlots}
                    blocks={message.answerBlocks ?? []}
                    markdownComponents={markdownComponents}
                    styles={styles}
                    isStreaming={isStreaming && !thinking?.isThinking}
                    hasLiveStreamed={hasLiveStreamed}
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
                    isStreaming={isStreaming && !thinking?.isThinking}
                    hasLiveStreamed={hasLiveStreamed}
                  />
                )}
                {/* Streaming cursor */}
                {isStreaming && !thinking?.isThinking && (
                  <span className={styles.streamingCursor} />
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
              <Tooltip title="複製訊息" color="#262626" styles={{ container: { color: '#ffffff' } }}>
                <button
                  className={styles.actionButton}
                  onClick={handleCopy}
                  aria-label="複製訊息"
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
                    <Tooltip title="這則回覆有幫助" color="#262626" styles={{ container: { color: '#ffffff' } }}>
                      <button
                        className={cx(
                          styles.actionButton,
                          isLiked && styles.actionButtonActive,
                        )}
                        disabled={isDisliked}
                        onClick={handleLikeFeedback}
                        aria-label="這則回覆有幫助"
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
                    <Tooltip title="這則回覆沒有幫助" color="#262626" styles={{ container: { color: '#ffffff' } }}>
                      <button
                        className={cx(
                          styles.actionButton,
                          isDisliked && styles.actionButtonActive,
                        )}
                        disabled={isLiked}
                        onClick={openDislikeFeedback}
                        aria-label="這則回覆沒有幫助"
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
                  <div className={styles.feedbackTitle}>分享回饋</div>

                  <div className={styles.mobileFeedbackReason}>
                    <div className={styles.feedbackLabel}>問題</div>
                    <select
                      aria-label="選取問題"
                      className={styles.mobileFeedbackNativeSelect}
                      onChange={(event) => setFeedbackReason(event.target.value as MessageFeedbackReason)}
                      value={feedbackReason ?? ''}
                    >
                      <option disabled value="">選取問題</option>
                      {FEEDBACK_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
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
                        {option.label}
                      </button>
                    ))}
                  </div>

                  <TextArea
                    className={styles.feedbackTextArea}
                    maxLength={2000}
                    onChange={(event) => setFeedbackComment(event.target.value)}
                    placeholder="分享詳細資料（選填）"
                    rows={isMobileFeedbackModal ? 8 : 4}
                    value={feedbackComment}
                  />

                  <div className={styles.feedbackPrivacyText}>
                    你的回饋將包含你的對話，以協助我們改善 AREQA。
                  </div>

                  <div className={styles.feedbackSubmitRow}>
                    <Button
                      className={styles.feedbackSubmitButton}
                      disabled={!feedbackReason}
                      loading={isFeedbackSubmitting}
                      onClick={submitDislikeFeedback}
                      type="primary"
                    >
                      提交
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
