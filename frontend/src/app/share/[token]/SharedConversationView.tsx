'use client';

import React, { useEffect, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { ArrowLeft, ExternalLink, Maximize2, X } from 'lucide-react';
import { normalizeDisplayMathBlocks, rehypeMathSource } from '@/utils/markdownMath';
import styles from './styles.module.css';

export interface SharedAnswerBlock {
  type: 'paragraph' | 'image_block';
  text?: string;
  imageUrl?: string;
  sourceUrl?: string;
  sourceDomain?: string;
  caption?: string;
  explanatoryCaption?: string;
  attributionString?: string;
  creator?: string;
}

export interface SharedMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  answerBlocks?: SharedAnswerBlock[] | null;
  citations?: string[] | null;
  createdAt: string;
}

export interface SharedConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: SharedMessage[];
}

function isSafeUrl(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    return ['http:', 'https:', 'mailto:'].includes(parsed.protocol);
  } catch {
    return url.startsWith('/') || url.startsWith('#');
  }
}

/**
 * Validate shared answer image URLs before rendering.
 *
 * Shared conversations can replay persisted backend image blocks. This helper
 * mirrors the chat view's browser-side guard so unsafe schemes never reach an
 * image element.
 */
function isSafeImageUrl(url: string | undefined): boolean {
  if (!url) return false;
  return (
    url.startsWith('http://') ||
    url.startsWith('https://') ||
    /^data:image\/(?:png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/=\s]+$/i.test(url)
  );
}

function SharedMarkdownTable({
  children,
  className,
  node,
  ...props
}: React.TableHTMLAttributes<HTMLTableElement> & { node?: unknown }) {
  void node;
  const [isExpanded, setIsExpanded] = useState(false);
  const tableClassName = [styles.markdownTable, className].filter(Boolean).join(' ');

  useEffect(() => {
    if (!isExpanded) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsExpanded(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExpanded]);

  return (
    <>
      <div className={styles.tableFrame}>
        <div className={styles.tableScroll} tabIndex={0}>
          <table className={tableClassName} {...props}>
            {children}
          </table>
        </div>
        <div className={styles.tableActions} aria-label="表格操作">
          <button
            aria-label="展開表格"
            className={styles.tableActionButton}
            title="展開表格"
            type="button"
            onClick={() => setIsExpanded(true)}
          >
            <Maximize2 size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      {isExpanded && (
        <div
          aria-label="展開的表格"
          aria-modal="true"
          className={styles.tableModalBackdrop}
          role="dialog"
          onMouseDown={() => setIsExpanded(false)}
        >
          <div
            className={styles.tableModalPanel}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className={styles.tableModalHeader}>
              <h2>表格</h2>
              <button
                aria-label="關閉表格"
                className={styles.tableModalClose}
                type="button"
                onClick={() => setIsExpanded(false)}
              >
                <X size={24} aria-hidden="true" strokeWidth={1.8} />
              </button>
            </div>
            <div className={styles.tableModalBody} tabIndex={0}>
              <table className={tableClassName} {...props}>
                {children}
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const markdownComponents: Components = {
  a: ({ href, children, ...props }) => {
    if (!isSafeUrl(href)) return <span>{children}</span>;
    return (
      <a href={href} rel="noopener noreferrer" target="_blank" {...props}>
        {children}
      </a>
    );
  },
  img: ({ src, alt, ...props }) => {
    const isValidSrc = typeof src === 'string' && (
      src.startsWith('http://') ||
      src.startsWith('https://') ||
      src.startsWith('data:image/')
    );
    if (!isValidSrc) return null;
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt={alt || ''} {...props} />;
  },
  table: SharedMarkdownTable,
  script: () => null,
  iframe: () => null,
  object: () => null,
  embed: () => null,
};

function SharedMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={markdownComponents}
      disallowedElements={['script', 'iframe', 'object', 'embed']}
      rehypePlugins={[[rehypeKatex, { throwOnError: false }], rehypeMathSource]}
      remarkPlugins={[remarkGfm, remarkMath]}
    >
      {normalizeDisplayMathBlocks(children)}
    </ReactMarkdown>
  );
}

/**
 * Render a shared answer image with an immersive source-aware viewer.
 *
 * Args:
 *   block: Persisted display metadata for a backend-verified answer image.
 *
 * Returns:
 *   A figure with a clickable thumbnail and an optional full-screen viewer.
 *
 * Compatibility:
 *   The shared page does not have the full chat style hook, so this component
 *   keeps the viewer self-contained in the CSS module while preserving the
 *   same source navigation behavior used by live conversations.
 */
function SharedImageBlockFigure({ block }: { block: SharedAnswerBlock }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const safeImageUrl = isSafeImageUrl(block.imageUrl) ? block.imageUrl : '';
  const safeSourceUrl = isSafeUrl(block.sourceUrl) ? block.sourceUrl : '';
  const caption = block.caption || block.explanatoryCaption || '';
  const sourceLabel = block.sourceDomain || 'Source';

  useEffect(() => {
    if (!isExpanded) return;

    // Keep shared image expansion keyboard-dismissable without coupling this
    // read-only page to the main chat modal stack.
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsExpanded(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExpanded]);

  if (!safeImageUrl) return null;

  return (
    <>
      <figure className={styles.imageBlock}>
        <button
          aria-label={caption ? `放大檢視圖片：${caption}` : '放大檢視圖片'}
          className={styles.imageBlockButton}
          type="button"
          onClick={() => setIsExpanded(true)}
        >
          {/* Shared answer images can come from many attributed providers, so Next Image cannot use a stable allowlist here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={safeImageUrl} alt={caption} />
        </button>
        {(caption || safeSourceUrl) && (
          <figcaption>
            {caption}
            {safeSourceUrl && (
              <>
                {' '}
                <a href={safeSourceUrl} rel="noreferrer" target="_blank">
                  {sourceLabel}
                </a>
              </>
            )}
          </figcaption>
        )}
      </figure>

      {isExpanded && (
        <div
          aria-label={caption || '圖片檢視'}
          aria-modal="true"
          className={styles.imageLightbox}
          role="dialog"
          onMouseDown={() => setIsExpanded(false)}
        >
          <button
            aria-label="關閉圖片檢視"
            className={styles.imageLightboxBack}
            type="button"
            onClick={() => setIsExpanded(false)}
          >
            <ArrowLeft size={24} aria-hidden="true" />
          </button>
          <button
            aria-label="關閉圖片檢視"
            className={styles.imageLightboxClose}
            type="button"
            onClick={() => setIsExpanded(false)}
          >
            <X size={20} aria-hidden="true" />
          </button>
          <div className={styles.imageLightboxStage} onMouseDown={(event) => event.stopPropagation()}>
            {safeSourceUrl ? (
              <a
                className={styles.imageLightboxImageLink}
                href={safeSourceUrl}
                rel="noreferrer"
                target="_blank"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={safeImageUrl} alt={caption} />
              </a>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={safeImageUrl} alt={caption} />
            )}
          </div>
          <div className={styles.imageLightboxMeta} onMouseDown={(event) => event.stopPropagation()}>
            {caption && <p className={styles.imageLightboxCaption}>{caption}</p>}
            {(block.attributionString || block.creator) && <p>{block.attributionString || block.creator}</p>}
            {safeSourceUrl && (
              <a
                className={styles.imageLightboxSource}
                href={safeSourceUrl}
                rel="noreferrer"
                target="_blank"
              >
                開啟原始來源
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function SharedAnswerBlocks({ blocks }: { blocks: SharedAnswerBlock[] }) {
  return blocks.map((block, index) => {
    if (block.type === 'paragraph' && block.text) {
      return <SharedMarkdown key={`paragraph-${index}`}>{block.text}</SharedMarkdown>;
    }

    if (block.type === 'image_block' && block.imageUrl) {
      return <SharedImageBlockFigure block={block} key={`image-${index}`} />;
    }

    return null;
  });
}

export function SharedConversationView({ conversation }: { conversation: SharedConversation }) {
  return (
    <main className={styles.page}>
      <section className={styles.chat}>
        <header className={styles.header}>
          <div className={styles.headerInner}>
            <div className={styles.brand}>AREQA</div>
            <h1>{conversation.title || 'Shared conversation'}</h1>
          </div>
        </header>

        <div className={styles.messages} tabIndex={0}>
          {conversation.messages.map((message) => (
            <article className={styles.message} data-role={message.role} key={message.id}>
              <div className={styles.bubbleWrapper}>
                {message.role === 'assistant' && (
                  <div className={styles.assistantLabel}>AREQA</div>
                )}
                <div className={styles.bubble}>
                  <div className={styles.content}>
                    {message.answerBlocks && message.answerBlocks.length > 0 ? (
                      <SharedAnswerBlocks blocks={message.answerBlocks} />
                    ) : (
                      <SharedMarkdown>{message.content}</SharedMarkdown>
                    )}
                    {message.citations && message.citations.length > 0 && (
                      <div className={styles.citations}>
                        {message.citations.map((citation) => (
                          isSafeUrl(citation) && (
                            <a href={citation} key={citation} rel="noreferrer" target="_blank">
                              {citation}
                            </a>
                          )
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
