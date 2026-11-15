import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@supabase/supabase-js';

const { updateUser } = vi.hoisted(() => ({ updateUser: vi.fn(async () => ({ error: null })) }));
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { updateUser } } }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));
const { sendOnboardingEvent } = vi.hoisted(() => ({ sendOnboardingEvent: vi.fn() }));
vi.mock('@/services/onboardingTelemetry', () => ({ sendOnboardingEvent }));

import { ONBOARDING_VERSION, hasSeenFeatureTour, hasSeenOnboarding, useOnboardingStore } from '@/store/onboarding';

const user = (metadata: Record<string, unknown> = {}) => ({ id: 'u1', user_metadata: metadata }) as unknown as User;

describe('onboarding store', () => {
  beforeEach(() => {
    window.localStorage.clear();
    updateUser.mockClear();
    sendOnboardingEvent.mockClear();
    useOnboardingStore.setState({ active: false, step: 0, waitingForAnswer: false, seen: [], branchId: null });
  });

  it('treats an account record or a local record as already seen', () => {
    expect(hasSeenOnboarding(user())).toBe(false);
    expect(hasSeenOnboarding(user({ areqa_onboarding: { version: ONBOARDING_VERSION, status: 'skipped' } }))).toBe(true);
    window.localStorage.setItem(`areqa:onboarding:v${ONBOARDING_VERSION}:u1`, '{}');
    expect(hasSeenOnboarding(user())).toBe(true);
  });

  it('hides while the first answer streams and advances when it completes', () => {
    const store = useOnboardingStore.getState();
    store.start();
    store.next();
    store.notify('question_sent');
    expect(useOnboardingStore.getState()).toMatchObject({ step: 1, waitingForAnswer: true });
    store.notify('answer_completed');
    expect(useOnboardingStore.getState()).toMatchObject({ step: 2, waitingForAnswer: false });
    store.notify('note_added');
    expect(useOnboardingStore.getState().step).toBe(3);
  });

  const stepIdNow = () => {
    const { steps, step } = useOnboardingStore.getState();
    return steps[step];
  };
  const goTo = (id: string) => {
    useOnboardingStore.setState((state) => ({ step: state.steps.indexOf(id as never) }));
  };

  it('walks from a saved note to the notes page and its note actions', () => {
    const store = useOnboardingStore.getState();
    store.start();
    goTo('addNote');
    store.notify('note_added');
    expect(stepIdNow()).toBe('notesEntry');
    store.notify('notes_opened');
    expect(stepIdNow()).toBe('notesFilters');
    store.next();
    expect(stepIdNow()).toBe('noteActions');
    store.next();
    expect(stepIdNow()).toBe('replyMore');
  });

  it('skips the note-card step when no note was saved during the tour', () => {
    const store = useOnboardingStore.getState();
    store.start();
    goTo('addNote');
    store.next();
    store.notify('notes_opened');
    store.next();
    expect(stepIdNow()).toBe('replyMore');
  });

  it('follows a real branch into the sidebar and inside it', () => {
    const store = useOnboardingStore.getState();
    store.start();
    goTo('replyMore');
    store.notify('branch_created', { conversationId: 'branch-1' });
    expect(stepIdNow()).toBe('branchSidebar');
    expect(useOnboardingStore.getState().branchId).toBe('branch-1');
    store.notify('branch_opened');
    expect(stepIdNow()).toBe('branchInside');
  });

  it('skips the branch walkthrough when the learner moves on without branching', () => {
    const store = useOnboardingStore.getState();
    store.start();
    goTo('replyMore');
    store.next();
    expect(stepIdNow()).toBe('composerPlus');
  });

  it('ignores events that do not belong to the current step', () => {
    const store = useOnboardingStore.getState();
    store.start();
    store.notify('note_added');
    store.notify('answer_completed');
    expect(useOnboardingStore.getState().step).toBe(0);
  });

  it('records the outcome on the account and locally so it never repeats', async () => {
    useOnboardingStore.getState().start();
    useOnboardingStore.getState().finish('skipped', user());

    expect(useOnboardingStore.getState().active).toBe(false);
    expect(updateUser).toHaveBeenCalledWith({ data: { areqa_onboarding: expect.objectContaining({ version: ONBOARDING_VERSION, status: 'skipped' }) } });
    expect(hasSeenOnboarding(user())).toBe(true);
  });

  it('builds a short tour of only the unused features for existing learners', () => {
    useOnboardingStore.getState().start('features', ['addNote', 'composerPlus']);
    expect(useOnboardingStore.getState()).toMatchObject({
      mode: 'features',
      steps: ['featuresIntro', 'addNote', 'notesEntry', 'notesFilters', 'noteActions', 'composerPlus', 'finish'],
      step: 0,
      featureCount: 2,
    });

    useOnboardingStore.getState().finish('completed', user());
    expect(updateUser).toHaveBeenCalledWith({ data: { areqa_feature_tour: expect.objectContaining({ status: 'completed' }) } });
    expect(hasSeenFeatureTour(user())).toBe(true);
    expect(hasSeenOnboarding(user())).toBe(false);
  });

  it('reports progress with step codes for drop-off analysis', () => {
    const store = useOnboardingStore.getState();
    store.start();
    store.next();
    store.finish('skipped', user());

    expect(sendOnboardingEvent.mock.calls.map(([event]) => event)).toEqual([
      { event: 'started', mode: 'full', step: 'welcome', stepIndex: 0, stepCount: 11 },
      { event: 'step_viewed', mode: 'full', step: 'ask', stepIndex: 1, stepCount: 11 },
      { event: 'finished', mode: 'full', step: 'ask', stepIndex: 1, stepCount: 11, outcome: 'skipped' },
    ]);
  });
});
