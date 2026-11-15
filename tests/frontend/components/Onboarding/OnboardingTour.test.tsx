import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { updateUser: vi.fn(async () => ({ error: null })) } } }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/onboardingTelemetry', () => ({ sendOnboardingEvent: vi.fn() }));
vi.mock('@/store/auth', () => ({
  useAuthStore: (selector: (state: { user: unknown }) => unknown) => selector({ user: { id: 'u1', user_metadata: {} } }),
}));

import { OnboardingTour } from '../../../../frontend/src/components/Onboarding/OnboardingTour';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';
import { useChatStore } from '@/store/chat';
import { useOnboardingStore } from '@/store/onboarding';

const renderTour = (onAskExample = vi.fn(), { withReplyButtons = true } = {}) => {
  render(
    <UserPreferencesProvider>
      <textarea data-tour="composer" aria-label="composer" />
      {withReplyButtons && <button type="button" data-tour="add-note">note</button>}
      <OnboardingTour onAskExample={onAskExample} />
    </UserPreferencesProvider>,
  );
  return onAskExample;
};

// jsdom has no layout; give tour anchors a stable on-screen box.
const STABLE_RECT = { top: 100, left: 100, width: 40, height: 32, right: 140, bottom: 132, x: 100, y: 100, toJSON: () => ({}) };

describe('OnboardingTour', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    useChatStore.setState({ isStreaming: false });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function rect(this: HTMLElement) {
      return (this.dataset.tour ? STABLE_RECT : { ...STABLE_RECT, width: 0, height: 0 }) as DOMRect;
    });
    HTMLElement.prototype.scrollIntoView = vi.fn();
    useOnboardingStore.setState({ active: false, step: 0, waitingForAnswer: false });
  });

  it('stays hidden until started', () => {
    renderTour();
    expect(screen.queryByText('歡迎來到 AREQA：懂你所學，伴你所讀')).not.toBeInTheDocument();
  });

  it('opens with what AREQA is for, then asks for a real question', async () => {
    const onAskExample = renderTour();
    act(() => useOnboardingStore.getState().start());

    expect(screen.getByText('歡迎來到 AREQA：懂你所學，伴你所讀')).toBeInTheDocument();
    expect(screen.getByText(/我可以把學習材料和觀念講解易懂清楚/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '開始（約 1 分鐘）' }));
    expect(await screen.findByText('你可以先問一個學習上的問題', undefined, { timeout: 3000 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '什麼是梯度下降？' }));
    expect(onAskExample).toHaveBeenCalledWith('什麼是梯度下降？');
  });

  it('steps aside while the answer streams and resumes at the notes step', async () => {
    renderTour();
    act(() => {
      useOnboardingStore.getState().start();
      useOnboardingStore.getState().next();
    });

    act(() => useChatStore.setState({ isStreaming: true }));
    expect(useOnboardingStore.getState().waitingForAnswer).toBe(true);
    act(() => useChatStore.setState({ isStreaming: false }));

    expect(useOnboardingStore.getState().step).toBe(2);
    expect(await screen.findByText('把重點存進筆記', undefined, { timeout: 3000 })).toBeInTheDocument();
  });

  it('can be skipped from any step', () => {
    renderTour();
    act(() => useOnboardingStore.getState().start());
    fireEvent.click(screen.getByRole('button', { name: '略過引導' }));
    expect(useOnboardingStore.getState().active).toBe(false);
  });

  it('runs the short existing-learner tour over only the unused features', async () => {
    renderTour();
    act(() => useOnboardingStore.getState().start('features', ['addNote']));

    expect(screen.getByText('你可能還沒用過這些功能')).toBeInTheDocument();
    expect(screen.getByText(/認識 1 個/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '看看' }));
    expect(await screen.findByText('把重點存進筆記', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.queryByText('你可以先問一個學習上的問題')).not.toBeInTheDocument();
  });

  it('keeps a step hidden until its button exists and has stopped moving', async () => {
    renderTour(vi.fn(), { withReplyButtons: false });
    act(() => useOnboardingStore.getState().start('features', ['addNote']));
    fireEvent.click(screen.getByRole('button', { name: '看看' }));

    // The reply toolbar has not rendered yet, so the highlight must not guess a position.
    await new Promise((resolve) => setTimeout(resolve, 700));
    expect(screen.queryByText('把重點存進筆記')).not.toBeInTheDocument();

    const button = document.createElement('button');
    button.dataset.tour = 'add-note';
    document.body.appendChild(button);
    expect(await screen.findByText('把重點存進筆記', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledWith({ block: 'center' });
    button.remove();
  });
});
