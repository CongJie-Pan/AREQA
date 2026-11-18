'use client';

/**
 * Step-by-step first-run guide.
 *
 * It opens with a one-line introduction of what AREQA is for, then asks the
 * learner to do things for real and explains what just happened:
 * - ask a question (the tour hides while the answer streams);
 * - save it as a note, find the notes from the sidebar and learn the notes
 *   page (filters, tags, edit, pin, jump back, delete);
 * - create a branch, spot it in the sidebar, open it and learn what the
 *   branch marker means;
 * - then the composer's "+" menu. Every step can skip the whole tour.
 *
 * The Topic Finder (選題) tour uses the same engine: what the workspace is for,
 * a real first message about the learner's pain point, then the topic card.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Button, Tour, type TourStepProps } from 'antd';
import { createStyles } from 'antd-style';
import { useUserPreferences, type TranslationKey } from '@/contexts/UserPreferencesContext';
import { useAuthStore } from '@/store/auth';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { isAskStep, useOnboardingStore, type OnboardingStepId } from '@/store/onboarding';

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

    /* Example questions can be long (English especially): wrap inside the popover. */
    .ant-btn {
      max-width: 100%;
      height: auto;
      min-height: 24px;
      padding-block: 2px;
      white-space: normal;
      text-align: start;
      overflow-wrap: anywhere;
    }
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
  notesEntry: 'account-menu',
  notesFilters: 'notes-filters',
  noteActions: 'note-card',
  replyMore: 'reply-more',
  branchInside: 'branch-boundary',
  composerPlus: 'composer-plus',
  tfAsk: 'composer',
  // Desktop: the topic card pane; phone: the "選題" badge that opens the drawer.
  tfCard: 'topic-card',
};

/** Steps shown on top of the notes page; leaving them returns to the chat. */
const NOTES_PAGE_STEPS: ReadonlySet<OnboardingStepId> = new Set(['notesFilters', 'noteActions']);
/** Steps that point into the sidebar, which is closed on phones. */
const SIDEBAR_STEPS: ReadonlySet<OnboardingStepId> = new Set(['notesEntry', 'branchSidebar']);

const EXAMPLE_KEYS: TranslationKey[] = ['onboardingExample1', 'onboardingExample2', 'onboardingExample3'];
const NOTE_ACTION_KEYS: TranslationKey[] = [
  'onboardingNoteActionTag', 'onboardingNoteActionEdit', 'onboardingNoteActionPin',
  'onboardingNoteActionSource', 'onboardingNoteActionDelete',
];
// The five questions, worded exactly as the topic card shows them.
const TOPIC_INTRO_KEYS: TranslationKey[] = ['topicStageTitle1', 'topicStageTitle2', 'topicStageTitle3', 'topicStageTitle4', 'topicStageTitle5'];
const TOPIC_EXAMPLE_KEYS: TranslationKey[] = ['topicTourExample1', 'topicTourExample2'];
const TOPIC_CARD_KEYS: TranslationKey[] = ['topicTourCardPoint1', 'topicTourCardPoint2', 'topicTourCardPoint3'];
const BRANCH_INSIDE_KEYS: TranslationKey[] = [
  'onboardingBranchInsideAbove', 'onboardingBranchInsideBelow', 'onboardingBranchInsideReturn',
];

function targetSelector(id: OnboardingStepId | undefined, branchId: string | null): string | undefined {
  if (id === 'branchSidebar') return branchId ? `[data-conversation-id="${branchId}"]` : undefined;
  const anchor = id ? TARGETS[id] : undefined;
  return anchor ? `[data-tour="${anchor}"]` : undefined;
}

/** Latest match = the newest reply. */
function latestAnchor(selector: string): HTMLElement | null {
  const matches = document.querySelectorAll<HTMLElement>(selector);
  return matches.length ? matches[matches.length - 1] : null;
}

function findTarget(selector: string | undefined): TourStepProps['target'] {
  if (!selector) return undefined;
  // A missing target centres the step instead.
  return (() => latestAnchor(selector)) as () => HTMLElement;
}

const TARGET_POLL_MS = 200;
const TARGET_STABLE_CHECKS = 2;
const TARGET_MAX_WAIT_MS = 8000;

/**
 * Report the step index once its target button exists, is visible and has
 * stopped moving (replies keep shifting while they reveal), scrolled to the
 * middle of the screen. Steps without a target are ready immediately.
 */
function useStepTargetReady(anchor: string | undefined, step: number, enabled: boolean): boolean {
  const [readyStep, setReadyStep] = useState<number | null>(null);

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

export interface OnboardingTourProps {
  onAskExample: (question: string) => void;
  /** Whether the notes page currently replaces the chat. */
  notesOpen: boolean;
  onOpenNotes: () => void;
  onCloseNotes: () => void;
  /** Make sure the sidebar is visible (it is a closed drawer on phones). */
  onOpenSidebar: () => void;
  onOpenConversation: (conversationId: string) => void;
}

export function OnboardingTour({
  onAskExample, notesOpen, onOpenNotes, onCloseNotes, onOpenSidebar, onOpenConversation,
}: OnboardingTourProps) {
  const { styles } = useStyles();
  const { t } = useUserPreferences();
  const user = useAuthStore((state) => state.user);
  const {
    active, steps: stepIds, step, featureCount, waitingForAnswer, branchId, next, notify, finish,
  } = useOnboardingStore();
  const isStreaming = useChatStore((state) => state.isStreaming);
  const activeConversationId = useConversationStore((state) => state.activeConversationId);
  const wasStreaming = useRef(false);
  const notesOpenRef = useRef(notesOpen);
  notesOpenRef.current = notesOpen;
  const stepId = stepIds[step];
  const selector = targetSelector(stepId, branchId);
  const isTargetReady = useStepTargetReady(selector, step, active && !waitingForAnswer);
  const isOpen = active && !waitingForAnswer && isTargetReady;
  useKeepHighlightAligned(isOpen);

  // Entering a step: show the sidebar it points into, or leave the notes page
  // once the notes steps are over. Runs on step changes only, so a learner who
  // opens notes on their own later is not interrupted.
  useEffect(() => {
    if (!active || !stepId) return;
    if (SIDEBAR_STEPS.has(stepId)) onOpenSidebar();
    if (notesOpenRef.current && stepId !== 'notesEntry' && !NOTES_PAGE_STEPS.has(stepId)) onCloseNotes();
    // Callbacks are recreated by the parent; the step is what matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, stepId]);

  // Real actions that finish a step.
  useEffect(() => {
    if (active && stepId === 'notesEntry' && notesOpen) notify('notes_opened');
  }, [active, notesOpen, notify, stepId]);
  useEffect(() => {
    if (active && stepId === 'branchSidebar' && branchId && activeConversationId === branchId) notify('branch_opened');
  }, [active, activeConversationId, branchId, notify, stepId]);

  // Ask steps advance on real activity: a stream starts, then finishes.
  useEffect(() => {
    if (!active || !isAskStep(stepId)) {
      wasStreaming.current = isStreaming;
      return;
    }
    if (isStreaming && !wasStreaming.current) notify('question_sent');
    if (!isStreaming && wasStreaming.current) notify('answer_completed');
    wasStreaming.current = isStreaming;
  }, [active, isStreaming, notify, stepId]);

  if (!active) return null;

  const skip = () => finish('skipped', user);
  const primaryButton = (label: TranslationKey, onClick: () => void) => (
    <Button autoInsertSpace={false} type="primary" size="small" onClick={onClick}>{t(label)}</Button>
  );
  const pointList = (keys: TranslationKey[]) => (
    <ul className={styles.points}>
      {keys.map((key) => <li key={key}>{t(key)}</li>)}
    </ul>
  );
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
        </div>
      ),
      actions: actions(<Button autoInsertSpace={false} type="primary" size="small" onClick={next}>{t('onboardingStart')}</Button>),
    },
    featuresIntro: {
      title: t('onboardingFeaturesTitle'),
      description: t('onboardingFeaturesBody', { count: Math.max(featureCount, 1) }),
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
    notesEntry: {
      title: t('onboardingNotesEntryTitle'),
      description: t('onboardingNotesEntryBody'),
      actions: actions(primaryButton('onboardingOpenForMe', onOpenNotes)),
    },
    notesFilters: {
      title: t('onboardingNotesFiltersTitle'),
      description: t('onboardingNotesFiltersBody'),
      actions: actions(primaryButton('onboardingNext', next)),
    },
    noteActions: {
      title: t('onboardingNoteActionsTitle'),
      description: (
        <div className={styles.body}>
          <span>{t('onboardingNoteActionsBody')}</span>
          {pointList(NOTE_ACTION_KEYS)}
        </div>
      ),
      actions: actions(primaryButton('onboardingBackToChat', next)),
    },
    replyMore: {
      title: t('onboardingBranchTitle'),
      description: (
        <div className={styles.body}>
          <span>{t('onboardingBranchBody')}</span>
          <span className={styles.lead}>{t('onboardingBranchTry')}</span>
        </div>
      ),
      actions: actions(<Button autoInsertSpace={false} size="small" onClick={next}>{t('onboardingNext')}</Button>),
    },
    branchSidebar: {
      title: t('onboardingBranchSidebarTitle'),
      description: t('onboardingBranchSidebarBody'),
      actions: actions(primaryButton('onboardingOpenForMe', () => { if (branchId) onOpenConversation(branchId); })),
    },
    branchInside: {
      title: t('onboardingBranchInsideTitle'),
      description: (
        <div className={styles.body}>
          {pointList(BRANCH_INSIDE_KEYS)}
        </div>
      ),
      actions: actions(primaryButton('onboardingGotIt', next)),
    },
    composerPlus: {
      title: t('onboardingPlusTitle'),
      description: t('onboardingPlusBody'),
      actions: actions(<Button autoInsertSpace={false} type="primary" size="small" onClick={next}>{t('onboardingNext')}</Button>),
    },
    tfIntro: {
      title: t('topicTourIntroTitle'),
      description: (
        <div className={styles.body}>
          <p className={styles.lead}>{t('topicTourIntroBody')}</p>
          <ol className={styles.points}>
            {TOPIC_INTRO_KEYS.map((key) => <li key={key}>{t(key)}</li>)}
          </ol>
          <span>{t('topicTourIntroPoint3')}</span>
        </div>
      ),
      actions: actions(primaryButton('topicTourStart', next)),
    },
    tfAsk: {
      title: t('topicTourAskTitle'),
      description: (
        <div className={styles.body}>
          <span>{t('topicTourAskBody')}</span>
          <div className={styles.examples}>
            {TOPIC_EXAMPLE_KEYS.map((key) => (
              <Button autoInsertSpace={false} key={key} size="small" onClick={() => onAskExample(t(key))}>{t(key)}</Button>
            ))}
          </div>
        </div>
      ),
      actions: actions(null),
    },
    tfCard: {
      // Beside the full-height card pane on desktop; under the badge on a phone.
      placement: typeof window !== 'undefined' && window.matchMedia?.('(max-width: 768px)').matches ? 'bottom' : 'left',
      title: t('topicTourCardTitle'),
      description: (
        <div className={styles.body}>
          <span>{t('topicTourCardBody')}</span>
          {pointList(TOPIC_CARD_KEYS)}
        </div>
      ),
      actions: actions(primaryButton('onboardingNext', next)),
    },
    tfFinish: {
      title: t('topicTourFinishTitle'),
      description: t('topicTourFinishBody'),
      actions: (
        <div className={styles.actions}>
          <span />
          <Button autoInsertSpace={false} type="primary" size="small" onClick={() => finish('completed', user)}>{t('onboardingDone')}</Button>
        </div>
      ),
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
    return { ...step, target: findTarget(targetSelector(id, branchId)) };
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
