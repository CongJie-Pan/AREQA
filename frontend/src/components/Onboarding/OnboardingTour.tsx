'use client';

/**
 * Step-by-step first-run guide.
 *
 * It opens with a one-line introduction of what AREQA is for, then asks the
 * learner to do things for real: ask a question (the tour hides while the
 * answer streams), save it as a note, then points at the branch menu and the
 * composer's "+" menu. Every step can skip the whole tour.
 */
import React, { useEffect, useRef } from 'react';
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

function findTarget(id: OnboardingStepId): TourStepProps['target'] {
  const anchor = TARGETS[id];
  if (!anchor) return undefined;
  // Latest match = the newest reply. A missing target centres the step instead.
  const lookup = () => {
    const matches = document.querySelectorAll<HTMLElement>(`[data-tour="${anchor}"]`);
    return matches.length ? matches[matches.length - 1] : null;
  };
  return lookup as () => HTMLElement;
}

export function OnboardingTour({ onAskExample }: { onAskExample: (question: string) => void }) {
  const { styles } = useStyles();
  const { t } = useUserPreferences();
  const user = useAuthStore((state) => state.user);
  const { active, steps: stepIds, step, waitingForAnswer, next, notify, finish } = useOnboardingStore();
  const isStreaming = useChatStore((state) => state.isStreaming);
  const wasStreaming = useRef(false);
  const stepId = stepIds[step];

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
      open={!waitingForAnswer}
      current={step}
      steps={steps}
      onClose={skip}
      indicatorsRender={(current, total) => <span>{current + 1} / {total}</span>}
      // antd 6 only honours actionsRender on the Tour itself, so pick per step here.
      actionsRender={(_original, { current }) => content[stepIds[current]].actions}
      zIndex={1200}
    />
  );
}
