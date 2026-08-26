'use client';

/**
 * RAGStatusPanel Component
 * Displays the real-time progress of the RAG retrieval pipeline with smooth animations
 */

import React, { memo } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { CitationSource } from '@/components/Citations';
import { useUserPreferences, type TranslationKey } from '@/contexts/UserPreferencesContext';
import { useStyles } from './styles';

export interface RAGInfo {
  status: 'idle' | 'routing' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done';
  message: string;
  sources: CitationSource[];
}

interface RAGStatusPanelProps {
  ragInfo: RAGInfo;
}

const STATUS_TRANSLATION_KEYS: Record<RAGInfo['status'], TranslationKey> = {
  idle: 'pipeline.defaultActive',
  routing: 'pipeline.routing',
  retrieving: 'pipeline.retrieving',
  searching_dense: 'pipeline.searchingDense',
  searching_sparse: 'pipeline.searchingSparse',
  reranking: 'pipeline.reranking',
  sources_ready: 'pipeline.sourcesReady',
  generating: 'pipeline.generating',
  done: 'pipeline.done',
};

/**
 * Resolves the frontend-owned translation key for a backend pipeline code.
 *
 * Args:
 *   status: Stable pipeline status code received from the backend stream.
 *
 * Returns:
 *   Translation key owned by the frontend language preference system.
 *
 * Compatibility:
 *   Backend status messages are intentionally ignored for primary UI copy so
 *   language switching remains deterministic and frontend-owned.
 */
function getStatusTranslationKey(status: RAGInfo['status']): TranslationKey {
  return STATUS_TRANSLATION_KEYS[status] ?? 'pipeline.defaultActive';
}

const RAGStatusPanelComponent = ({ ragInfo }: RAGStatusPanelProps) => {
  const { styles } = useStyles();
  const { t } = useUserPreferences();

  const hasSources = ragInfo.sources.length > 0;
  const statusText = t(getStatusTranslationKey(ragInfo.status));

  // The transcript should stay quiet for generic model waiting states. Render
  // this panel only when the backend has actual RAG source evidence to show.
  if (!hasSources) return null;

  return (
    <motion.div
      className={styles.container}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className={styles.header}>
        <div className={styles.statusInfo}>
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          >
            <CheckCircle2 size={18} className={styles.checkIcon} />
          </motion.div>
          
          <div style={{ overflow: 'hidden', height: '24px', position: 'relative' }}>
            <AnimatePresence mode="wait">
              <motion.span
                key={`${ragInfo.status}:${statusText}`}
                className={styles.statusText}
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: -20, opacity: 0 }}
                transition={{ duration: 0.2 }}
                style={{ display: 'block', whiteSpace: 'nowrap' }}
              >
                {statusText}
              </motion.span>
            </AnimatePresence>
          </div>
        </div>

        <AnimatePresence>
          <motion.div
            className={styles.sourceCount}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 10 }}
          >
            {t('pipeline.sourceCount', { count: ragInfo.sources.length })}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  );
};

export const RAGStatusPanel = memo(RAGStatusPanelComponent);
