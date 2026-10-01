import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthPrompt } from '@/components/Auth';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { supabase } from '@/lib/supabase';

let authStateCallback: ((event: string, session: unknown) => void) | null = null;

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn((callback) => {
        authStateCallback = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
    },
  },
}));

vi.mock('@supabase/auth-ui-react', () => ({
  Auth: ({ view }: { view: string }) => <div data-testid={`supabase-auth-${view}`} />,
}));

vi.mock('@supabase/auth-ui-shared', () => ({ ThemeSupa: {} }));

describe('AuthPrompt', () => {
  const renderPrompt = (onDismiss: () => void) => render(
    <UserPreferencesProvider><AuthPrompt open onDismiss={onDismiss} /></UserPreferencesProvider>,
  );

  beforeEach(() => {
    authStateCallback = null;
    vi.clearAllMocks();
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: null } } as never);
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('shows the guest prompt actions', async () => {
    const onDismiss = vi.fn();
    renderPrompt(onDismiss);

    expect(await screen.findByText('歡迎來到 AREQA')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '登入' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '註冊' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '維持登出狀態' })).toBeInTheDocument();
  });

  it('lets guests choose a language from the sign-in prompt', () => {
    window.localStorage.removeItem('areqa:interface-language');
    renderPrompt(vi.fn());

    const languageGroup = screen.getByRole('group', { name: 'Language' });
    fireEvent.click(within(languageGroup).getByRole('button', { name: '繁體中文' }));

    expect(window.localStorage.getItem('areqa:interface-language')).toBe('zh-TW');
    expect(screen.getByRole('button', { name: '登入' })).toBeInTheDocument();
  });

  it('opens the selected authentication view and dismisses on guest choice', async () => {
    const onDismiss = vi.fn();
    renderPrompt(onDismiss);

    fireEvent.click(await screen.findByRole('button', { name: '登入' }));
    expect(screen.getByTestId('supabase-auth-sign_in')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    fireEvent.click(screen.getByRole('button', { name: '維持登出狀態' }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('dismisses immediately when Supabase reports a signed-in session', async () => {
    const onDismiss = vi.fn();
    renderPrompt(onDismiss);

    await screen.findByText('歡迎來到 AREQA');
    await act(async () => {
      authStateCallback?.('SIGNED_IN', { user: { id: 'user-1' } });
    });

    await waitFor(() => expect(onDismiss).toHaveBeenCalledOnce());
  });
});
