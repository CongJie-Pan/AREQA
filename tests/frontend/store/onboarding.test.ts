import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@supabase/supabase-js';

const { updateUser } = vi.hoisted(() => ({ updateUser: vi.fn(async () => ({ error: null })) }));
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { updateUser } } }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { ONBOARDING_VERSION, hasSeenOnboarding, useOnboardingStore } from '@/store/onboarding';

const user = (metadata: Record<string, unknown> = {}) => ({ id: 'u1', user_metadata: metadata }) as unknown as User;

describe('onboarding store', () => {
  beforeEach(() => {
    window.localStorage.clear();
    updateUser.mockClear();
    useOnboardingStore.setState({ active: false, step: 0, waitingForAnswer: false });
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
});
