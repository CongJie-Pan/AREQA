/**
 * Guided tour state.
 *
 * Two modes share one engine:
 * - `full`: first-run, learn-by-doing tour for new accounts.
 * - `features`: a short tour for existing learners covering only the features
 *   they have not used yet.
 *
 * Some steps wait for a real action (a sent question, a saved note) instead of
 * a "Next" click. Outcomes are stored on the Supabase account
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

export type OnboardingStepId = 'welcome' | 'featuresIntro' | 'ask' | 'addNote' | 'replyMore' | 'composerPlus' | 'finish';
export type OnboardingMode = 'full' | 'features';
export type OnboardingEvent = 'question_sent' | 'answer_completed' | 'note_added';
export type OnboardingOutcome = 'completed' | 'skipped';

/** Feature steps that the existing-learner tour can pick from. */
export type FeatureStepId = Extract<OnboardingStepId, 'addNote' | 'replyMore' | 'composerPlus'>;

export const ONBOARDING_STEPS: readonly OnboardingStepId[] = ['welcome', 'ask', 'addNote', 'replyMore', 'composerPlus', 'finish'];

const RECORD_KEYS: Record<OnboardingMode, string> = { full: 'areqa_onboarding', features: 'areqa_feature_tour' };

interface OnboardingState {
  active: boolean;
  mode: OnboardingMode;
  steps: readonly OnboardingStepId[];
  step: number;
  /** While true the tour is hidden so the learner can read a streaming answer. */
  waitingForAnswer: boolean;
  start: (mode?: OnboardingMode, featureSteps?: readonly FeatureStepId[]) => void;
  next: () => void;
  notify: (event: OnboardingEvent) => void;
  finish: (outcome: OnboardingOutcome, user: User | null) => void;
}

function storageKey(mode: OnboardingMode, userId: string): string {
  return `areqa:${mode === 'full' ? 'onboarding' : 'feature-tour'}:v${ONBOARDING_VERSION}:${userId}`;
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
  waitingForAnswer: false,

  start: (mode = 'full', featureSteps = []) => {
    const steps: readonly OnboardingStepId[] = mode === 'full'
      ? ONBOARDING_STEPS
      : ['featuresIntro', ...featureSteps, 'finish'];
    set({ active: true, mode, steps, step: 0, waitingForAnswer: false });
    report('started', get());
  },

  next: () => {
    set((state) => ({ step: Math.min(state.step + 1, state.steps.length - 1) }));
    report('step_viewed', get());
  },

  notify: (event) => {
    const { active, steps, step } = get();
    if (!active) return;
    const current = steps[step];
    if (current === 'ask' && event === 'question_sent') {
      set({ waitingForAnswer: true });
    } else if (current === 'ask' && event === 'answer_completed') {
      set({ waitingForAnswer: false, step: step + 1 });
      report('step_viewed', get());
    } else if (current === 'addNote' && event === 'note_added') {
      set({ step: step + 1 });
      report('step_viewed', get());
    }
  },

  finish: (outcome, user) => {
    const state = get();
    report('finished', state, outcome);
    set({ active: false, step: 0, waitingForAnswer: false });
    if (user) recordOnboardingOutcome(state.mode, outcome, user);
  },
}));
