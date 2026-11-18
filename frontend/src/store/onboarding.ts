/**
 * Guided tour state.
 *
 * Two modes share one engine:
 * - `full`: first-run, learn-by-doing tour for new accounts.
 * - `features`: a short tour for existing learners covering only the features
 *   they have not used yet.
 * - `topicFinder`: shown the first time a learner opens the Topic Finder (選題)
 *   workspace; it waits for their first real answer before showing the topic card.
 *
 * Some steps wait for a real action (a sent question, a saved note, opening
 * the notes panel, creating or opening a branch) instead of a "Next" click.
 * Follow-up steps that only make sense after such an action are skipped when
 * the learner moves on without doing it. Outcomes are stored on the Supabase account
 * (`user_metadata`) so a tour never repeats across devices, with localStorage
 * as an offline fallback. Progress events go to the backend for drop-off
 * analysis and carry fixed step codes only.
 */
import { create } from 'zustand';
import type { User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import { logger } from '@/utils/logger';
import { sendOnboardingEvent } from '@/services/onboardingTelemetry';

/** Bump to re-run a tour for everyone after a major redesign. */
export const ONBOARDING_VERSION = 1;

export type OnboardingStepId =
  | 'welcome' | 'featuresIntro' | 'ask'
  | 'addNote' | 'notesEntry' | 'notesFilters' | 'noteActions'
  | 'replyMore' | 'branchSidebar' | 'branchInside'
  | 'composerPlus' | 'finish'
  | 'tfIntro' | 'tfAsk' | 'tfCard' | 'tfFinish';
export type OnboardingMode = 'full' | 'features' | 'topicFinder';
export type OnboardingEvent =
  | 'question_sent' | 'answer_completed' | 'note_added' | 'notes_opened' | 'branch_created' | 'branch_opened';
export type OnboardingOutcome = 'completed' | 'skipped';

/** Feature steps that the existing-learner tour can pick from. */
export type FeatureStepId = Extract<OnboardingStepId, 'addNote' | 'replyMore' | 'composerPlus'>;

/** Each feature expands into the steps that walk through it. */
const FEATURE_STEPS: Record<FeatureStepId, readonly OnboardingStepId[]> = {
  addNote: ['addNote', 'notesEntry', 'notesFilters', 'noteActions'],
  replyMore: ['replyMore', 'branchSidebar', 'branchInside'],
  composerPlus: ['composerPlus'],
};

export const ONBOARDING_STEPS: readonly OnboardingStepId[] = [
  'welcome', 'ask', ...FEATURE_STEPS.addNote, ...FEATURE_STEPS.replyMore, ...FEATURE_STEPS.composerPlus, 'finish',
];

/** Topic Finder tour: what it is, start with a pain point, then the topic card. */
export const TOPIC_FINDER_STEPS: readonly OnboardingStepId[] = ['tfIntro', 'tfAsk', 'tfCard', 'tfFinish'];

/** Steps that wait for a real question and its answer instead of a "Next" click. */
const ASK_STEPS: ReadonlySet<OnboardingStepId> = new Set(['ask', 'tfAsk']);
export const isAskStep = (step: OnboardingStepId | undefined): boolean => Boolean(step && ASK_STEPS.has(step));

/** Real actions that complete a step and move the tour on. */
const ADVANCES_ON: Partial<Record<OnboardingStepId, OnboardingEvent>> = {
  addNote: 'note_added',
  notesEntry: 'notes_opened',
  replyMore: 'branch_created',
  branchSidebar: 'branch_opened',
};

/** Steps that need an earlier action; without it there is nothing to show. */
const REQUIRES: Partial<Record<OnboardingStepId, OnboardingEvent>> = {
  noteActions: 'note_added',
  branchSidebar: 'branch_created',
  branchInside: 'branch_created',
};

function nextStepIndex(steps: readonly OnboardingStepId[], from: number, seen: readonly OnboardingEvent[]): number {
  let index = from + 1;
  while (index < steps.length - 1) {
    const required = REQUIRES[steps[index]];
    if (!required || seen.includes(required)) break;
    index += 1;
  }
  return Math.min(index, steps.length - 1);
}

const RECORD_KEYS: Record<OnboardingMode, string> = {
  full: 'areqa_onboarding', features: 'areqa_feature_tour', topicFinder: 'areqa_topic_finder_tour',
};
const STORAGE_NAMES: Record<OnboardingMode, string> = {
  full: 'onboarding', features: 'feature-tour', topicFinder: 'topic-finder-tour',
};

interface OnboardingState {
  active: boolean;
  mode: OnboardingMode;
  steps: readonly OnboardingStepId[];
  step: number;
  /** Number of features covered (the tour itself has more steps). */
  featureCount: number;
  /** While true the tour is hidden so the learner can read a streaming answer. */
  waitingForAnswer: boolean;
  /** Real actions the learner already did during this tour. */
  seen: readonly OnboardingEvent[];
  /** Branch created during the tour, highlighted in the sidebar. */
  branchId: string | null;
  start: (mode?: OnboardingMode, featureSteps?: readonly FeatureStepId[]) => void;
  next: () => void;
  notify: (event: OnboardingEvent, detail?: { conversationId?: string }) => void;
  finish: (outcome: OnboardingOutcome, user: User | null) => void;
}

function storageKey(mode: OnboardingMode, userId: string): string {
  return `areqa:${STORAGE_NAMES[mode]}:v${ONBOARDING_VERSION}:${userId}`;
}

function hasRecord(user: User, mode: OnboardingMode): boolean {
  const record = user.user_metadata?.[RECORD_KEYS[mode]] as { version?: number } | undefined;
  if (record && typeof record.version === 'number' && record.version >= ONBOARDING_VERSION) return true;
  try {
    return window.localStorage.getItem(storageKey(mode, user.id)) !== null;
  } catch {
    return false;
  }
}

/** Whether this account already completed or skipped the first-run tour. */
export function hasSeenOnboarding(user: User): boolean {
  return hasRecord(user, 'full');
}

/** Whether this account already answered the "features you may not know" offer. */
export function hasSeenFeatureTour(user: User): boolean {
  return hasRecord(user, 'features');
}

/** Whether this account already completed or skipped the Topic Finder tour. */
export function hasSeenTopicFinderTour(user: User): boolean {
  return hasRecord(user, 'topicFinder');
}

/** Store a tour outcome locally and on the account (fail-soft). */
export function recordOnboardingOutcome(mode: OnboardingMode, outcome: OnboardingOutcome, user: User): void {
  const record = { version: ONBOARDING_VERSION, status: outcome, at: new Date().toISOString() };
  try {
    window.localStorage.setItem(storageKey(mode, user.id), JSON.stringify(record));
  } catch {
    // Private mode: the account record below still prevents repeats.
  }
  void (async () => supabase.auth.updateUser({ data: { [RECORD_KEYS[mode]]: record } }))().then((result) => {
    if (result?.error) logger.warn('onboarding_persist_failed', { component: 'onboarding', mode, reason: result.error.name });
  }).catch(() => undefined);
}

function report(event: 'started' | 'step_viewed' | 'finished', state: Pick<OnboardingState, 'mode' | 'steps' | 'step'>, outcome?: OnboardingOutcome) {
  sendOnboardingEvent({
    event,
    mode: state.mode,
    step: state.steps[state.step],
    stepIndex: state.step,
    stepCount: state.steps.length,
    ...(outcome ? { outcome } : {}),
  });
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  active: false,
  mode: 'full',
  steps: ONBOARDING_STEPS,
  step: 0,
  featureCount: 0,
  waitingForAnswer: false,
  seen: [],
  branchId: null,

  start: (mode = 'full', featureSteps = []) => {
    const steps: readonly OnboardingStepId[] = mode === 'full'
      ? ONBOARDING_STEPS
      : mode === 'topicFinder'
        ? TOPIC_FINDER_STEPS
        : ['featuresIntro', ...featureSteps.flatMap((id) => FEATURE_STEPS[id]), 'finish'];
    set({
      active: true, mode, steps, step: 0, featureCount: featureSteps.length,
      waitingForAnswer: false, seen: [], branchId: null,
    });
    report('started', get());
  },

  next: () => {
    set((state) => ({ step: nextStepIndex(state.steps, state.step, state.seen) }));
    report('step_viewed', get());
  },

  notify: (event, detail) => {
    const { active, steps, step, seen } = get();
    if (!active) return;
    const current = steps[step];
    if (isAskStep(current) && event === 'question_sent') {
      set({ waitingForAnswer: true });
      return;
    }
    if (isAskStep(current) && event === 'answer_completed') {
      set({ waitingForAnswer: false, step: step + 1 });
      report('step_viewed', get());
      return;
    }
    const nextSeen = seen.includes(event) ? seen : [...seen, event];
    set({
      seen: nextSeen,
      ...(event === 'branch_created' && detail?.conversationId ? { branchId: detail.conversationId } : {}),
    });
    if (ADVANCES_ON[current] === event) {
      set({ step: nextStepIndex(steps, step, nextSeen) });
      report('step_viewed', get());
    }
  },

  finish: (outcome, user) => {
    const state = get();
    report('finished', state, outcome);
    set({ active: false, step: 0, waitingForAnswer: false, seen: [], branchId: null });
    if (user) recordOnboardingOutcome(state.mode, outcome, user);
  },
}));
