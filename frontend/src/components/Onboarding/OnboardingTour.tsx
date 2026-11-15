'use client';

/**
 * Step-by-step first-run guide.
 *
 * It opens with a one-line introduction of what AREQA is for, then asks the
 * learner to do things for real: ask a question (the tour hides while the
 * answer streams), save it as a note, then points at the branch menu and the
 * composer's "+" menu. Every step can skip the whole tour.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Button, Tour, type TourStepProps } from 'antd';
import { createStyles } from 'antd-style';
import { useUserPreferences, type TranslationKey } from '@/contexts/UserPreferencesContext';
import { useAuthStore } from '@/store/auth';
import { useChatStore } from '@/store/chat';
import { useOnboardingStore, type OnboardingStepId } from '@/store/onboarding';

const useStyles = createStyles(({ css }) => ({
  body: css`
    display: flex;
    flex-direction: column;
    gap: 10px;
    line-height: 1.6;
  `,
  lead: css`
    margin: 0;
    font-weight: 600;
  `,
  points: css`
    margin: 0;
    padding-left: 18px;

    li + li {
      margin-top: 4px;
    }
  `,
  examples: css`
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  `,
  actions: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    width: 100%;
  `,
}));

/** `data-tour` anchors placed on the real controls. */
const TARGETS: Partial<Record<OnboardingStepId, string>> = {
  ask: 'composer',
  addNote: 'add-note',
  replyMore: 'reply-more',
  composerPlus: 'composer-plus',
};

const EXAMPLE_KEYS: TranslationKey[] = ['onboardingExample1', 'onboardingExample2', 'onboardingExample3'];

/** Latest match = the newest reply. */
function latestAnchor(anchor: string): HTMLElement | null {
  const matches = document.querySelectorAll<HTMLElement>(`[data-tour="${anchor}"]`);
  return matches.length ? matches[matches.length - 1] : null;
}

function findTarget(id: OnboardingStepId): TourStepProps['target'] {
  const anchor = TARGETS[id];
  if (!anchor) return undefined;
  // A missing target centres the step instead.
  return (() => latestAnchor(anchor)) as () => HTMLElement;
}

const TARGET_POLL_MS = 200;
const TARGET_STABLE_CHECKS = 2;
const TARGET_MAX_WAIT_MS = 8000;

/**
 * Report the step index once its target button exists, is visible and has
 * stopped moving (replies keep shifting while they reveal), scrolled to the
 * middle of the screen. Steps without a target are ready immediately.
 */
function useStepTargetReady(stepId: OnboardingStepId | undefined, step: number, enabled: boolean): boolean {
  const [readyStep, setReadyStep] = useState<number | null>(null);
  const anchor = stepId ? TARGETS[stepId] : undefined;

  useEffect(() => {
    if (!enabled || !anchor) return undefined;
    let previous = '';
    let stableChecks = 0;
    const startedAt = Date.now();
    let settleTimer: number | undefined;
    const poll = window.setInterval(() => {
      const element = latestAnchor(anchor);
      const rect = element?.getBoundingClientRect();
      const signature = rect && rect.width > 0 && rect.height > 0
        ? `${Math.round(rect.top)}:${Math.round(rect.left)}:${Math.round(rect.width)}:${Math.round(rect.height)}`
        : '';
      stableChecks = signature && signature === previous ? stableChecks + 1 : 0;
      previous = signature;
      if (stableChecks < TARGET_STABLE_CHECKS && Date.now() - startedAt < TARGET_MAX_WAIT_MS) return;
      window.clearInterval(poll);
      element?.scrollIntoView({ block: 'center' });
      // Let the scroll land before the highlight measures the button.
      settleTimer = window.setTimeout(() => setReadyStep(step), 150);
    }, TARGET_POLL_MS);
    return () => {
      window.clearInterval(poll);
      window.clearTimeout(settleTimer);
    };
  }, [anchor, enabled, step]);

  return !anchor || readyStep === step;
}

/**
 * The highlight only re-measures on window scroll/resize. Messages scroll
 * inside their own container and replies change size, so forward those as a
 * window scroll while a step is open.
 */
function useKeepHighlightAligned(open: boolean): void {
  useEffect(() => {
    if (!open) return undefined;
    let frame = 0;
    const nudge = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        window.dispatchEvent(new Event('scroll'));
      });
    };
    document.addEventListener('scroll', nudge, true);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(nudge);
    observer?.observe(document.body);
    return () => {
      document.removeEventListener('scroll', nudge, true);
      observer?.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, [open]);
}

export function OnboardingTour({ onAskExample }: { onAskExample: (question: string) => void }) {
  const { styles } = useStyles();
  const { t } = useUserPreferences();
  const user = useAuthStore((state) => state.user);
  const { active, steps: stepIds, step, waitingForAnswer, next, notify, finish } = useOnboardingStore();
  const isStreaming = useChatStore((state) => state.isStreaming);
  const wasStreaming = useRef(false);
  const stepId = stepIds[step];
  const isTargetReady = useStepTargetReady(stepId, step, active && !waitingForAnswer);
  const isOpen = active && !waitingForAnswer && isTargetReady;
  useKeepHighlightAligned(isOpen);

  // The "ask" step advances on real activity: a stream starts, then finishes.
  useEffect(() => {
    if (!active || stepId !== 'ask') {
      wasStreaming.current = isStreaming;
      return;
    }
    if (isStreaming && !wasStreaming.current) notify('question_sent');
    if (!isStreaming && wasStreaming.current) notify('answer_completed');
    wasStreaming.current = isStreaming;
  }, [active, isStreaming, notify, stepId]);

  if (!active) return null;

  const skip = () => finish('skipped', user);
  const actions = (primary: React.ReactNode) => (
    <div className={styles.actions}>
      <Button autoInsertSpace={false} type="text" size="small" onClick={skip}>{t('onboardingSkip')}</Button>
      {primary}
    </div>
  );

  const content: Record<OnboardingStepId, Omit<TourStepProps, 'target'> & { actions: React.ReactNode }> = {
    welcome: {
      title: t('onboardingWelcomeTitle'),
      description: (
        <div className={styles.body}>
          <p className={styles.lead}>{t('onboardingPitch')}</p>
          <ul className={styles.points}>
            <li>{t('onboardingPointConcise')}</li>
            <li>{t('onboardingPointGuided')}</li>
            <li>{t('onboardingPointAdaptive')}</li>
          </ul>
        </div>
      ),
      actions: actions(<Button autoInsertSpace={false} type="primary" size="small" onClick={next}>{t('onboardingStart')}</Button>),
    },
    featuresIntro: {
      title: t('onboardingFeaturesTitle'),
      description: t('onboardingFeaturesBody', { count: Math.max(stepIds.length - 2, 1) }),
      actions: actions(<Button autoInsertSpace={false} type="primary" size="small" onClick={next}>{t('onboardingFeaturesStart')}</Button>),
    },
    ask: {
      title: t('onboardingAskTitle'),
      description: (
        <div className={styles.body}>
          <span>{t('onboardingAskBody')}</span>
          <div className={styles.examples}>
            {EXAMPLE_KEYS.map((key) => (
              <Button autoInsertSpace={false} key={key} size="small" onClick={() => onAskExample(t(key))}>{t(key)}</Button>
            ))}
          </div>
        </div>
      ),
      actions: actions(null),
    },
    addNote: {
      title: t('onboardingNoteTitle'),
      description: t('onboardingNoteBody'),
      actions: actions(<Button autoInsertSpace={false} size="small" onClick={next}>{t('onboardingNext')}</Button>),
    },
    replyMore: {
      title: t('onboardingBranchTitle'),
      description: t('onboardingBranchBody'),
      actions: actions(<Button autoInsertSpace={false} type="primary" size="small" onClick={next}>{t('onboardingGotIt')}</Button>),
    },
    composerPlus: {
      title: t('onboardingPlusTitle'),
      description: t('onboardingPlusBody'),
      actions: actions(<Button autoInsertSpace={false} type="primary" size="small" onClick={next}>{t('onboardingNext')}</Button>),
    },
    finish: {
      title: t('onboardingFinishTitle'),
      description: t('onboardingFinishBody'),
      actions: (
        <div className={styles.actions}>
          <span />
          <Button autoInsertSpace={false} type="primary" size="small" onClick={() => finish('completed', user)}>{t('onboardingDone')}</Button>
        </div>
      ),
    },
  };

  const steps: TourStepProps[] = stepIds.map((id) => {
    const { actions: _actions, ...step } = content[id];
    void _actions;
    return { ...step, target: findTarget(id) };
  });

  return (
    <Tour
      open={isOpen}
      current={step}
      steps={steps}
      onClose={skip}
      indicatorsRender={(current, total) => <span>{current + 1} / {total}</span>}
      // antd 6 only honours actionsRender on the Tour itself, so pick per step here.
      actionsRender={(_original, { current }) => content[stepIds[current]].actions}
      // Below antd dropdowns (1050) so menus opened from a highlighted button stay clickable.
      zIndex={1030}
    />
  );
}
