import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { updateUser: vi.fn(async () => ({ error: null })) } } }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));
vi.mock('@/store/auth', () => ({
  useAuthStore: (selector: (state: { user: unknown }) => unknown) => selector({ user: { id: 'u1', user_metadata: {} } }),
}));

import { OnboardingTour } from '../../../../frontend/src/components/Onboarding/OnboardingTour';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';
import { useChatStore } from '@/store/chat';
import { useOnboardingStore } from '@/store/onboarding';

const renderTour = (onAskExample = vi.fn()) => {
  render(
    <UserPreferencesProvider>
      <textarea data-tour="composer" aria-label="composer" />
      <OnboardingTour onAskExample={onAskExample} />
    </UserPreferencesProvider>,
  );
  return onAskExample;
};

describe('OnboardingTour', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    useChatStore.setState({ isStreaming: false });
    useOnboardingStore.setState({ active: false, step: 0, waitingForAnswer: false });
  });

  it('stays hidden until started', () => {
    renderTour();
    expect(screen.queryByText('歡迎來到 AREQA')).not.toBeInTheDocument();
  });

  it('opens with what AREQA is for, then asks for a real question', () => {
    const onAskExample = renderTour();
    act(() => useOnboardingStore.getState().start());

    expect(screen.getByText('歡迎來到 AREQA')).toBeInTheDocument();
    expect(screen.getByText(/把難懂的東西用最少的話講到你聽得懂/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '開始（約 1 分鐘）' }));
    expect(screen.getByText('先問一個學習上的問題')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '什麼是自我效能？' }));
    expect(onAskExample).toHaveBeenCalledWith('什麼是自我效能？');
  });

  it('steps aside while the answer streams and resumes at the notes step', () => {
    renderTour();
    act(() => {
      useOnboardingStore.getState().start();
      useOnboardingStore.getState().next();
    });

    act(() => useChatStore.setState({ isStreaming: true }));
    expect(useOnboardingStore.getState().waitingForAnswer).toBe(true);
    act(() => useChatStore.setState({ isStreaming: false }));

    expect(useOnboardingStore.getState().step).toBe(2);
    expect(screen.getByText('把重點存進筆記')).toBeInTheDocument();
  });

  it('can be skipped from any step', () => {
    renderTour();
    act(() => useOnboardingStore.getState().start());
    fireEvent.click(screen.getByRole('button', { name: '略過引導' }));
    expect(useOnboardingStore.getState().active).toBe(false);
  });
});
