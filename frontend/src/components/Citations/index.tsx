'use client';

/**
 * Citations Component
 * Displays citation links from AI response
 */

import React, { useState, useCallback } from 'react';
import { ChevronRight, ExternalLink, BookOpen, Quote } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Modal, Divider } from 'antd';
import { useStyles } from './styles';

export interface CitationSource {
  title: string;
  snippet: string;
  score: number;
  chunk_id: string;
}

export interface CitationsProps {
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

/**
 * Citations displays reference links from AI response
 */
export function Citations({
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
                {sources!.map((src, index) => (
                  <div 
                    key={src.chunk_id || index} 
                    className={styles.sourceCard}
                    onClick={() => openSourceModal(src)}
                  >
                    <div className={styles.sourceHeader}>
                      <span className={styles.linkNumber}>{index + 1}</span>
                      <span className={styles.sourceTitle}>{src.title || '古籍文獻'}</span>
                    </div>
                    <div className={styles.sourceSnippet}>
                      {src.snippet}
                    </div>
                  </div>
                ))}
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
                  >
                    <span className={styles.linkNumber}>{index + 1}</span>
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
            margin: 0
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
        {selectedSource && (
          <div style={{ padding: '4px 0' }}>
            <div style={{ marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#ffffff' }}>{selectedSource.title}</h3>
              <div style={{ marginTop: '4px', color: 'rgba(255, 255, 255, 0.45)', fontSize: '12px' }}>
                識別碼: {selectedSource.chunk_id}
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
              fontSize: '15px',
              color: '#f0f0f0'
            }}>
              <Quote size={24} style={{ position: 'absolute', top: '10px', left: '8px', opacity: 0.2, color: '#ff4d4f' }} />
              <div style={{ position: 'relative', zIndex: 1 }}>
                {selectedSource.snippet}
              </div>
            </div>
            
            <div style={{ marginTop: '20px', textAlign: 'right', fontSize: '12px', color: '#bfbfbf' }}>
              * 以上內容為 RAG 檢索之原文片段
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

export default Citations;
