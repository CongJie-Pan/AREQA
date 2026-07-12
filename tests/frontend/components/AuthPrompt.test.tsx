import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthPrompt } from '@/components/Auth';
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
  beforeEach(() => {
    authStateCallback = null;
    vi.clearAllMocks();
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: null } } as never);
  });

  it('shows the guest prompt actions', async () => {
    const onDismiss = vi.fn();
    render(<AuthPrompt open onDismiss={onDismiss} />);

    expect(await screen.findByText('歡迎來到 AREQA')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '登入' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '註冊' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '維持登出狀態' })).toBeInTheDocument();
  });

  it('opens the selected authentication view and dismisses on guest choice', async () => {
    const onDismiss = vi.fn();
    render(<AuthPrompt open onDismiss={onDismiss} />);

    fireEvent.click(await screen.findByRole('button', { name: '登入' }));
    expect(screen.getByTestId('supabase-auth-sign_in')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    fireEvent.click(screen.getByRole('button', { name: '維持登出狀態' }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('dismisses immediately when Supabase reports a signed-in session', async () => {
    const onDismiss = vi.fn();
    render(<AuthPrompt open onDismiss={onDismiss} />);

    await screen.findByText('歡迎來到 AREQA');
    await act(async () => {
      authStateCallback?.('SIGNED_IN', { user: { id: 'user-1' } });
    });

    await waitFor(() => expect(onDismiss).toHaveBeenCalledOnce());
  });
});
