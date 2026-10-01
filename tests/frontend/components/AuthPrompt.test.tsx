import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthPrompt } from '@/components/Auth';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { supabase } from '@/lib/supabase';
import { useAuthStore } from '@/store/auth';

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
    useAuthStore.setState({ user: null, isInitialized: false });
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: null } } as never);
    window.localStorage.removeItem('areqa:interface-language');
  });

  it('shows the guest prompt actions', async () => {
    const onDismiss = vi.fn();
    renderPrompt(onDismiss);

    expect(await screen.findByText('Welcome to AREQA')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign up' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stay signed out' })).toBeInTheDocument();
  });

  it('keeps a previously selected language without offering guest selection', () => {
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    renderPrompt(vi.fn());

    expect(screen.queryByRole('group', { name: '語言' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem('areqa:interface-language')).toBe('zh-TW');
    expect(screen.getByRole('button', { name: '登入' })).toBeInTheDocument();
  });

  it('opens the selected authentication view and dismisses on guest choice', async () => {
    const onDismiss = vi.fn();
    renderPrompt(onDismiss);

    fireEvent.click(await screen.findByRole('button', { name: 'Log in' }));
    expect(screen.getByTestId('supabase-auth-sign_in')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    fireEvent.click(screen.getByRole('button', { name: 'Stay signed out' }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('dismisses immediately when Supabase reports a signed-in session', async () => {
    const onDismiss = vi.fn();
    renderPrompt(onDismiss);

    await screen.findByText('Welcome to AREQA');
    await act(async () => {
      authStateCallback?.('SIGNED_IN', { user: { id: 'user-1' } });
    });

    await waitFor(() => expect(onDismiss).toHaveBeenCalledOnce());
  });
});
