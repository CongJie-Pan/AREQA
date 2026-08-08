'use client';

/**
 * Citations Component
 * Displays citation links from AI response
 */

import React, { useState, useCallback } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronRight, ExternalLink, BookOpen, Quote } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Modal, Divider } from 'antd';
import { useStyles } from './styles';

export interface CitationSource {
  title: string;
  snippet: string;
  score?: number;
  chunk_id: string;
  url?: string;
}

export interface CitationsProps {
  /** The ID of the message this citation block belongs to */
  messageId: string;
  /** Array of citation URLs (legacy) */
  citations?: string[];
  /** Structured RAG sources (new) */
  sources?: CitationSource[];
  /** Whether expanded by default */
  defaultExpanded?: boolean;
  /** Class name for styling */
  className?: string;
}

/**
 * Extract domain from URL for display
 * Validates URL protocol for security
 */
function getDomain(url: string): string {
  try {
    const urlObj = new URL(url);
    // Validate it's http(s) protocol for security
    if (!['http:', 'https:'].includes(urlObj.protocol)) {
      return 'Invalid URL';
    }
    return urlObj.hostname.replace('www.', '');
  } catch {
    return 'Invalid URL';
  }
}

function getSourceUrl(src: CitationSource): string {
  const candidate = src.url || src.chunk_id || '';
  try {
    const urlObj = new URL(candidate);
    return ['http:', 'https:'].includes(urlObj.protocol) ? urlObj.toString() : '';
  } catch {
    return '';
  }
}

/**
 * Validate Markdown links before rendering source text.
 *
 * Args:
 *   url: Raw href emitted by the Markdown parser.
 *
 * Returns:
 *   True when the href is safe to attach to the DOM. Source snippets come from
 *   retrieval providers, so we only allow user-inspectable web/mail links and
 *   local anchors instead of executable or browser-privileged protocols.
 */
function isSafeMarkdownUrl(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const urlObj = new URL(url);
    return ['http:', 'https:', 'mailto:'].includes(urlObj.protocol);
  } catch {
    return url.startsWith('#') || url.startsWith('/');
  }
}

const citationMarkdownComponents: Components = {
  a: ({ href, children }) => {
    if (!isSafeMarkdownUrl(href)) {
      return <span>{children}</span>;
    }

    return (
      <a
        href={href}
        target={href?.startsWith('#') ? undefined : '_blank'}
        rel={href?.startsWith('#') ? undefined : 'noopener noreferrer'}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </a>
    );
  },
};

/**
 * Render citation provider text as constrained Markdown.
 *
 * Args:
 *   content: Source title or snippet from the retrieval backend.
 *   className: Presentation class for the target citation surface.
 *
 * Returns:
 *   A Markdown-rendered block with raw HTML skipped and unsafe elements removed.
 */
function CitationMarkdown({ content, className }: { content: string; className: string }) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={citationMarkdownComponents}
        disallowedElements={['img', 'script', 'iframe', 'object', 'embed']}
        skipHtml
        unwrapDisallowed
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Citations displays reference links from AI response
 */
export function Citations({
  messageId,
  citations,
  sources,
  defaultExpanded = false,
  className,
}: CitationsProps) {
  const { styles, cx } = useStyles();
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [selectedSource, setSelectedSource] = useState<CitationSource | null>(null);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const openSourceModal = useCallback((src: CitationSource) => {
    setSelectedSource(src);
  }, []);

  const closeSourceModal = useCallback(() => {
    setSelectedSource(null);
  }, []);

  // Listen for scoped open-citation events from MessageItem
  React.useEffect(() => {
    const handleOpenCitation = (e: Event) => {
      const customEvent = e as CustomEvent<{ index: number }>;
      const idx = customEvent.detail.index - 1; // 1-based to 0-based
      if (sources && idx >= 0 && idx < sources.length) {
        setSelectedSource(sources[idx]);
        // Also expand the citations panel if it's not already
        if (!isExpanded) setIsExpanded(true);
      }
    };
    const eventName = `open-citation-${messageId}`;
    window.addEventListener(eventName, handleOpenCitation);
    return () => {
      window.removeEventListener(eventName, handleOpenCitation);
    };
  }, [sources, messageId, isExpanded]);

  // Handle keyboard navigation for accessibility
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleExpanded();
      }
    },
    [toggleExpanded]
  );

  // Don't render if no sources or citations
  const hasSources = sources && sources.length > 0;
  const hasCitations = citations && citations.length > 0;
  if (!hasSources && !hasCitations) {
    return null;
  }

  const count = hasSources ? sources.length : (citations ? citations.length : 0);

  return (
    <div className={cx(styles.container, className)}>
      <div
        className={styles.header}
        onClick={toggleExpanded}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        aria-label={`${isExpanded ? 'Hide' : 'Show'} ${count} sources`}
      >
        <ChevronRight
          size={14}
          className={cx(styles.icon, isExpanded && styles.iconExpanded)}
          aria-hidden="true"
        />
        <BookOpen size={14} className={styles.icon} aria-hidden="true" />
        <span>文獻來源</span>
        <span className={styles.count}>({count})</span>
      </div>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {hasSources ? (
              <div className={styles.sourcesGrid}>
                {sources!.map((src, index) => {
                  const sourceUrl = getSourceUrl(src);
                  const domain = sourceUrl ? getDomain(sourceUrl) : '';
                  return (
                    <div
                      key={src.chunk_id || sourceUrl || index}
                      className={styles.sourceCard}
                      onClick={() => openSourceModal(src)}
                    >
                      <div className={styles.sourceHeader}>
                        <span className={styles.linkNumber}>{index + 1}</span>
                        {sourceUrl && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={`https://www.google.com/s2/favicons?domain=${domain}&sz=32`}
                            alt="favicon"
                            style={{ width: '16px', height: '16px', borderRadius: '50%' }}
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none';
                            }}
                          />
                        )}
                        <CitationMarkdown
                          className={styles.sourceTitle}
                          content={src.title || domain || '文獻來源'}
                        />
                        {sourceUrl && (
                          <a
                            href={sourceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              width: '24px',
                              height: '24px',
                              borderRadius: '50%',
                              background: 'rgba(255, 255, 255, 0.1)',
                              color: 'rgba(255, 255, 255, 0.65)',
                              transition: 'all 0.2s',
                              marginLeft: 'auto'
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)';
                              e.currentTarget.style.color = '#ffffff';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                              e.currentTarget.style.color = 'rgba(255, 255, 255, 0.65)';
                            }}
                            title="在新分頁開啟原文"
                          >
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                      <CitationMarkdown className={styles.sourceSnippet} content={src.snippet} />
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className={styles.list}>
                {citations!.map((url, index) => (
                  <a
                    key={`${url}-${index}`}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.link}
                    title={url}
                    style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                  >
                    <span className={styles.linkNumber}>{index + 1}</span>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`https://www.google.com/s2/favicons?domain=${getDomain(url)}&sz=32`}
                      alt="favicon"
                      style={{ width: '16px', height: '16px', borderRadius: '50%' }}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                    <span className={styles.linkText}>{getDomain(url)}</span>
                    <ExternalLink size={12} className={styles.linkIcon} />
                  </a>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Source Detail Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BookOpen size={18} style={{ color: '#ff4d4f' }} />
            <span style={{ color: '#ffffff' }}>文獻原文詳情</span>
          </div>
        }
        open={!!selectedSource}
        onCancel={closeSourceModal}
        footer={null}
        centered
        width={600}
        styles={{
          mask: { backdropFilter: 'blur(4px)' },
          container: {
            borderRadius: '16px',
            background: '#262626',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            padding: 0,
            overflow: 'hidden'
          },
          body: {
            background: '#262626',
            padding: '20px',
            margin: 0,
            maxHeight: '70vh',
            overflowY: 'auto'
          },
          header: {
            background: '#262626',
            borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
            padding: '16px 20px',
            margin: 0
          },
          footer: {
            background: '#262626',
            margin: 0,
            padding: 0,
            border: 'none'
          }
        }}
      >
        {selectedSource && (() => {
          const selectedSourceUrl = getSourceUrl(selectedSource);
          return (
            <div style={{ padding: '4px 0' }}>
              <div style={{ marginBottom: '16px' }}>
                <CitationMarkdown
                  className={styles.modalSourceTitle}
                  content={selectedSource.title || '文獻來源'}
                />
                <div style={{ marginTop: '6px', display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                  {selectedSourceUrl ? (
                    <>
                      <a
                        href={selectedSourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={selectedSourceUrl}
                        style={{
                          minWidth: 0,
                          color: 'rgba(255, 255, 255, 0.62)',
                          fontSize: '12px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          textDecoration: 'none'
                        }}
                      >
                        來源: {selectedSourceUrl}
                      </a>
                      <a
                        href={selectedSourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="在新分頁開啟文獻原文"
                        aria-label="在新分頁開啟文獻原文"
                        style={{
                          flexShrink: 0,
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: '24px',
                          height: '24px',
                          borderRadius: '50%',
                          background: 'rgba(255, 255, 255, 0.08)',
                          color: 'rgba(255, 255, 255, 0.75)'
                        }}
                      >
                        <ExternalLink size={12} />
                      </a>
                    </>
                  ) : (
                    <span style={{ color: 'rgba(255, 255, 255, 0.45)', fontSize: '12px' }}>
                      識別碼: {selectedSource.chunk_id}
                    </span>
                  )}
                </div>
              </div>
              <Divider style={{ margin: '12px 0', borderColor: 'rgba(255, 255, 255, 0.05)' }} />

              <div style={{
                position: 'relative',
                padding: '16px 20px',
                background: '#333333',
                borderRadius: '12px',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                lineHeight: 1.8,
                fontSize: '16px',
                color: '#f0f0f0'
              }}>
                <Quote size={24} style={{ position: 'absolute', top: '10px', left: '8px', opacity: 0.2, color: '#ff4d4f' }} />
                <CitationMarkdown className={styles.modalSourceSnippet} content={selectedSource.snippet} />
              </div>

              <div style={{ marginTop: '20px', textAlign: 'right', fontSize: '12px', color: '#bfbfbf' }}>
                * 以上內容為 RAG 檢索之原文片段
              </div>
            </div>
          );
        })()}
      </Modal>
    </div>
  );
}

export default Citations;
