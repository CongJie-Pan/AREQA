/**
 * First-run guided tour state.
 *
 * The tour teaches by doing: some steps wait for a real action (a sent
 * question, a saved note) instead of a "Next" click. Completion is stored on
 * the Supabase account (`user_metadata.areqa_onboarding`) so it never repeats
 * across devices, with localStorage as an offline fallback.
 */
import { create } from 'zustand';
import type { User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import { logger } from '@/utils/logger';

/** Bump to re-run the tour for everyone after a major redesign. */
export const ONBOARDING_VERSION = 1;

export const ONBOARDING_STEPS = ['welcome', 'ask', 'addNote', 'replyMore', 'composerPlus', 'finish'] as const;
export type OnboardingStepId = typeof ONBOARDING_STEPS[number];
export type OnboardingEvent = 'question_sent' | 'answer_completed' | 'note_added';
type OnboardingOutcome = 'completed' | 'skipped';

interface OnboardingState {
  active: boolean;
  step: number;
  /** While true the tour is hidden so the learner can read a streaming answer. */
  waitingForAnswer: boolean;
  start: () => void;
  next: () => void;
  notify: (event: OnboardingEvent) => void;
  finish: (outcome: OnboardingOutcome, user: User | null) => void;
}

function storageKey(userId: string): string {
  return `areqa:onboarding:v${ONBOARDING_VERSION}:${userId}`;
}

/** Whether this account already completed or skipped the current tour. */
export function hasSeenOnboarding(user: User): boolean {
  const record = user.user_metadata?.areqa_onboarding as { version?: number } | undefined;
  if (record && typeof record.version === 'number' && record.version >= ONBOARDING_VERSION) return true;
  try {
    return window.localStorage.getItem(storageKey(user.id)) !== null;
  } catch {
    return false;
  }
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  active: false,
  step: 0,
  waitingForAnswer: false,

  start: () => {
    logger.info('onboarding_started', { component: 'onboarding', version: ONBOARDING_VERSION });
    set({ active: true, step: 0, waitingForAnswer: false });
  },

  next: () => set((state) => ({ step: Math.min(state.step + 1, ONBOARDING_STEPS.length - 1) })),

  notify: (event) => {
    const { active, step } = get();
    if (!active) return;
    const current = ONBOARDING_STEPS[step];
    if (current === 'ask' && event === 'question_sent') set({ waitingForAnswer: true });
    else if (current === 'ask' && event === 'answer_completed') set({ waitingForAnswer: false, step: step + 1 });
    else if (current === 'addNote' && event === 'note_added') set({ step: step + 1 });
  },

  finish: (outcome, user) => {
    const { step } = get();
    // Step ids only; never learner text.
    logger.info('onboarding_finished', { component: 'onboarding', outcome, step: ONBOARDING_STEPS[step] });
    set({ active: false, step: 0, waitingForAnswer: false });
    if (!user) return;
    const record = { version: ONBOARDING_VERSION, status: outcome, at: new Date().toISOString() };
    try {
      window.localStorage.setItem(storageKey(user.id), JSON.stringify(record));
    } catch {
      // Private mode: the account record below still prevents repeats.
    }
    void supabase.auth.updateUser({ data: { areqa_onboarding: record } }).then(({ error }) => {
      if (error) logger.warn('onboarding_persist_failed', { component: 'onboarding', reason: error.name });
    }).catch(() => undefined);
  },
}));
