'use client';

/**
 * TurnProgress
 *
 * One quiet line beside the waiting assistant message ("Analyzing figures 2/4 · 9s ›"),
 * expandable into the steps already completed. Step codes come from the backend
 * `progress` SSE event; all wording is frontend-owned so language switching stays
 * deterministic.
 */

import React, { memo, useEffect, useState } from 'react';
import { Check, ChevronRight } from 'lucide-react';
import { createStyles, keyframes } from 'antd-style';
import type { TurnProgressStep } from '@/services/chat-stream/types';
import type { TurnProgressEntry } from '@/store/chat/types';
import { useUserPreferences, type TranslationKey } from '@/contexts/UserPreferencesContext';

const STEP_KEYS: Record<TurnProgressStep, TranslationKey> = {
  uploading: 'progress.uploading',
  reading_attachments: 'progress.readingAttachments',
  analyzing: 'progress.analyzing',
  recalling_memory: 'progress.recallingMemory',
  planning: 'progress.planning',
  web_search: 'progress.webSearch',
  visual_planning: 'progress.visualPlanning',
  visual_understanding: 'progress.visualUnderstanding',
  reading_documents: 'progress.readingDocuments',
  composing: 'progress.composing',
};

/** Steps whose counts read naturally as "done/total" after the label. */
const COUNTED_STEPS: ReadonlySet<TurnProgressStep> = new Set(['visual_planning', 'visual_understanding']);

/** Elapsed time is shown only once a wait is long enough to feel slow. */
const ELAPSED_VISIBLE_AFTER_MS = 3000;

const blink = keyframes`
  0%, 80%, 100% { opacity: 0.25; transform: scale(0.85); }
  40% { opacity: 1; transform: scale(1); }
`;

const shimmer = keyframes`
  0% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
`;

const useStyles = createStyles(({ css, token }) => ({
  container: css`
    margin: 4px 0 12px;
    font-size: 14px;
    line-height: 22px;
    color: ${token.colorTextSecondary};
  `,
  row: css`
    display: inline-flex;
    align-items: center;
    gap: 10px;
    max-width: 100%;
    padding: 2px 0;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;

    &:hover .turn-progress-chevron {
      color: ${token.colorText};
    }
  `,
  dots: css`
    display: inline-flex;
    gap: 3px;
    flex: none;

    & > span {
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: ${token.colorPrimary};
      animation: ${blink} 1.2s infinite ease-in-out;
    }
    & > span:nth-of-type(2) { animation-delay: 0.15s; }
    & > span:nth-of-type(3) { animation-delay: 0.3s; }

    @media (prefers-reduced-motion: reduce) {
      & > span { animation: none; opacity: 0.8; }
    }
  `,
  label: css`
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    background: linear-gradient(
      90deg,
      ${token.colorTextSecondary} 0%,
      ${token.colorTextSecondary} 40%,
      ${token.colorText} 50%,
      ${token.colorTextSecondary} 60%,
      ${token.colorTextSecondary} 100%
    );
    background-size: 300% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: ${shimmer} 2.2s linear infinite;

    @media (prefers-reduced-motion: reduce) {
      animation: none;
      -webkit-text-fill-color: currentColor;
    }
  `,
  meta: css`
    flex: none;
    color: ${token.colorTextTertiary};
    font-variant-numeric: tabular-nums;
  `,
  chevron: css`
    flex: none;
    color: ${token.colorTextTertiary};
    transition: transform 0.2s ${token.motionEaseOut}, color 0.2s;
  `,
  chevronOpen: css`
    transform: rotate(90deg);
  `,
  steps: css`
    list-style: none;
    margin: 6px 0 0;
    padding: 0 0 0 4px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 13px;
  `,
  step: css`
    display: flex;
    align-items: center;
    gap: 8px;
  `,
  stepDone: css`
    color: ${token.colorTextTertiary};
  `,
  stepIcon: css`
    flex: none;
    width: 14px;
    display: inline-flex;
    justify-content: center;
    color: ${token.colorSuccess};
  `,
  activeDot: css`
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: ${token.colorPrimary};
  `,
}));

export interface TurnProgressProps {
  /** Steps reported for the current turn, oldest first. */
  steps: TurnProgressEntry[];
  /** Whether the user's turn carried attachments (affects the first, local step). */
  hasAttachments?: boolean;
}

/**
 * Resolve the learner-facing label for a step, including counts when meaningful.
 *
 * Args:
 *   entry: Progress step with optional counts.
 *   t: Frontend translation function.
 *
 * Returns:
 *   Label text and an optional "current/total" suffix.
 */
export function describeStep(
  entry: Pick<TurnProgressEntry, 'step' | 'current' | 'total'>,
  t: (key: TranslationKey, params?: Record<string, string | number>) => string,
): { label: string; count?: string } {
  if (entry.step === 'reading_documents' && entry.total) {
    return { label: t('progress.readingDocumentsCount', { count: entry.total }) };
  }
  if (entry.step === 'reading_attachments' && entry.total) {
    return { label: t('progress.readingAttachmentsCount', { count: entry.total }) };
  }
  const label = t(STEP_KEYS[entry.step] ?? 'progress.analyzing');
  if (COUNTED_STEPS.has(entry.step) && entry.total) {
    return { label, count: `${Math.min(entry.current ?? 0, entry.total)}/${entry.total}` };
  }
  return { label };
}

const TurnProgressComponent = ({ steps, hasAttachments = false }: TurnProgressProps) => {
  const { styles, cx } = useStyles();
  const { t } = useUserPreferences();
  const [expanded, setExpanded] = useState(false);
  // The first backend frame can take seconds while uploads are parsed, so a
  // local first step keeps the line visible from the moment the user sends.
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const localFirst: TurnProgressEntry = {
    step: hasAttachments ? 'uploading' : 'analyzing',
    startedAt: mountedAt,
  };
  const timeline = steps.length > 0 ? steps : [localFirst];
  const current = timeline[timeline.length - 1];
  const completed = timeline.slice(0, -1);
  const { label, count } = describeStep(current, t);
  const elapsedMs = now - Math.min(mountedAt, timeline[0].startedAt);
  const elapsed = elapsedMs >= ELAPSED_VISIBLE_AFTER_MS
    ? t('progress.elapsed', { seconds: Math.floor(elapsedMs / 1000) })
    : '';
  const meta = [count, elapsed].filter(Boolean).join(' · ');

  return (
    <div className={styles.container} role="status" aria-live="polite" data-testid="turn-progress">
      <button
        type="button"
        className={styles.row}
        aria-expanded={expanded}
        aria-label={expanded ? t('progress.hideSteps') : t('progress.showSteps')}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className={styles.dots} aria-hidden="true"><span /><span /><span /></span>
        <span className={styles.label} data-testid="turn-progress-label">{label}</span>
        {meta && <span className={styles.meta} data-testid="turn-progress-meta">{meta}</span>}
        <ChevronRight
          size={14}
          aria-hidden="true"
          className={cx('turn-progress-chevron', styles.chevron, expanded && styles.chevronOpen)}
        />
      </button>
      {expanded && (
        <ol className={styles.steps} data-testid="turn-progress-steps">
          {completed.map((entry, index) => {
            const done = describeStep(entry, t);
            return (
              <li key={`${entry.step}-${index}`} className={cx(styles.step, styles.stepDone)}>
                <span className={styles.stepIcon}><Check size={12} aria-hidden="true" /></span>
                {done.label}{done.count ? ` ${done.count}` : ''}
              </li>
            );
          })}
          <li className={styles.step} aria-current="step">
            <span className={styles.stepIcon}><span className={styles.activeDot} /></span>
            {label}{count ? ` ${count}` : ''}
          </li>
        </ol>
      )}
    </div>
  );
};

export const TurnProgress = memo(TurnProgressComponent);
