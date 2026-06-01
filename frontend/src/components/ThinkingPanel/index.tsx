'use client';

/**
 * ThinkingPanel Component
 * Collapsible panel for displaying AI thinking process
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { App, Button, Tooltip } from 'antd';
import { ChevronRight, Copy, Brain } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStyles } from './styles';

export interface ThinkingPanelProps {
  /** Thinking content text */
  content?: string;
  /** Thinking duration in milliseconds */
  duration?: number;
  /** Whether AI is currently thinking */
  isThinking?: boolean;
  /** Whether panel is expanded by default */
  defaultExpanded?: boolean;
  /** Class name for styling */
  className?: string;
}

/**
 * Format duration in seconds
 */
function formatDuration(ms: number): string {
  const seconds = ms / 1000;
  return `${seconds.toFixed(1)}s`;
}

/**
 * ThinkingPanel displays AI reasoning process in a collapsible panel
 */
export function ThinkingPanel({
  content = '',
  duration,
  isThinking = false,
  defaultExpanded = true,
  className,
}: ThinkingPanelProps) {
  const { styles, cx } = useStyles();
  const [isExpanded, setIsExpanded] = useState(() => defaultExpanded || isThinking);
  const [liveTime, setLiveTime] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number | null>(null);
  const { message } = App.useApp();

  // Track live thinking time
  // Update every 500ms instead of 100ms to reduce unnecessary re-renders
  useEffect(() => {
    if (isThinking) {
      startTimeRef.current = Date.now();
      const interval = setInterval(() => {
        if (startTimeRef.current) {
          setLiveTime(Date.now() - startTimeRef.current);
        }
      }, 500);

      return () => {
        clearInterval(interval);
        startTimeRef.current = null;
        // Reset liveTime asynchronously to avoid synchronous setState in effect
        setTimeout(() => setLiveTime(0), 0);
      };
    }
  }, [isThinking]);

  // Auto-expand when thinking starts — driven by prop change, no effect needed
  // (initial value already set via useState(() => defaultExpanded || isThinking))
  useEffect(() => {
    if (isThinking) {
      // Defer to next tick to avoid synchronous setState in effect body
      const id = setTimeout(() => setIsExpanded(true), 0);
      return () => clearTimeout(id);
    }
  }, [isThinking]);

  // Auto-scroll to bottom when content updates
  useEffect(() => {
    if (contentRef.current && isExpanded) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [content, isExpanded]);

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (content) {
      try {
        await navigator.clipboard.writeText(content);
        message.success('已複製到剪貼簿');
      } catch {
        message.error('複製失敗');
      }
    }
  }, [content]);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
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

  // Display duration: live time when thinking, final duration when done
  const displayDuration = isThinking ? liveTime : duration;

  // Don't render if no content and not thinking
  if (!content && !isThinking) {
    return null;
  }

  return (
    <div className={cx(styles.container, className)}>
      <div
        className={styles.header}
        onClick={toggleExpanded}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        aria-label={`${isExpanded ? '收合' : '展開'} 思考過程細節`}
      >
        <div className={styles.headerLeft}>
          <ChevronRight
            size={16}
            className={cx(styles.icon, isExpanded && styles.iconExpanded)}
          />
          <Brain size={16} className={styles.icon} />

          {isThinking ? (
            <span className={styles.thinkingLabel}>
              <span className={styles.shinyText}>思考中</span>
              <span className={styles.thinkingIndicator}>
                <span className={styles.dot} />
                <span className={styles.dot} />
                <span className={styles.dot} />
              </span>
            </span>
          ) : (
            <span className={styles.thinkingLabel}>思考過程</span>
          )}
        </div>

        <div className={styles.headerRight}>
          {displayDuration !== undefined && displayDuration > 0 && (
            <span className={styles.duration}>
              {isThinking ? '思考時長 ' : '思考共耗時 '}
              {formatDuration(displayDuration)}
            </span>
          )}

          {content && !isThinking && (
            <Tooltip title="複製思考內容">
              <Button
                type="text"
                size="small"
                icon={<Copy size={14} />}
                className={styles.copyButton}
                onClick={handleCopy}
              />
            </Tooltip>
          )}
        </div>
      </div>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div ref={contentRef} className={styles.content}>
              {/* trimStart() removes leading newlines that may leak through
                  from the backend's artificial <think>\n injection */}
              {content.trimStart() || (
                <span className={styles.emptyContent}>
                  AI 正在分析您的問題...
                </span>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default ThinkingPanel;
