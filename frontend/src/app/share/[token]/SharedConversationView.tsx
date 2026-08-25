'use client';

import React, { useEffect, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Maximize2, X } from 'lucide-react';
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

function SharedAnswerBlocks({ blocks }: { blocks: SharedAnswerBlock[] }) {
  return blocks.map((block, index) => {
    if (block.type === 'paragraph' && block.text) {
      return <SharedMarkdown key={`paragraph-${index}`}>{block.text}</SharedMarkdown>;
    }

    if (block.type === 'image_block' && block.imageUrl) {
      return (
        <figure className={styles.imageBlock} key={`image-${index}`}>
          {/* Shared answer images can come from many attributed providers, so Next Image cannot use a stable allowlist here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={block.imageUrl} alt={block.caption || block.explanatoryCaption || ''} />
          {(block.caption || block.explanatoryCaption || block.sourceUrl) && (
            <figcaption>
              {block.explanatoryCaption || block.caption}
              {block.sourceUrl && isSafeUrl(block.sourceUrl) && (
                <>
                  {' '}
                  <a href={block.sourceUrl} rel="noreferrer" target="_blank">
                    {block.sourceDomain || 'Source'}
                  </a>
                </>
              )}
            </figcaption>
          )}
        </figure>
      );
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
