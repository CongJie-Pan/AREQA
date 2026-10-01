import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { UserAuthUI } from '@/components/Auth';
import { supabase } from '@/lib/supabase';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { useAuthStore } from '@/store/auth';

const supabaseMocks = vi.hoisted(() => ({
  insertFeedback: vi.fn(),
  authUiProps: vi.fn(),
}));

const matchMediaListeners = new Map<string, (event: MediaQueryListEvent) => void>();

// Mock matchMedia for Ant Design Modal and the user preference provider.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // Deprecated
    removeListener: vi.fn(), // Deprecated
    addEventListener: vi.fn((eventName: string, listener: (event: MediaQueryListEvent) => void) => {
      if (eventName === 'change') matchMediaListeners.set(query, listener);
    }),
    removeEventListener: vi.fn((eventName: string) => {
      if (eventName === 'change') matchMediaListeners.delete(query);
    }),
    dispatchEvent: vi.fn(),
  })),
});

// Mock Dependencies
vi.mock('@/lib/supabase', () => {
  let onAuthStateChangeCallback: any = null;
  
  return {
    supabase: {
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
        getUser: vi.fn().mockResolvedValue({ data: { user: null }, error: null }),
        onAuthStateChange: vi.fn((callback) => {
          onAuthStateChangeCallback = callback;
          return { data: { subscription: { unsubscribe: vi.fn() } } };
        }),
        signOut: vi.fn().mockResolvedValue({ error: null }),
        updateUser: vi.fn(),
      },
      from: vi.fn(() => ({
        insert: supabaseMocks.insertFeedback,
      })),
      // Expose a helper to trigger auth state changes in tests
      _triggerAuthStateChange: (event: string, session: any) => {
        if (onAuthStateChangeCallback) {
          onAuthStateChangeCallback(event, session);
        }
      }
    }
  };
});

vi.mock('@supabase/auth-ui-react', () => ({
  Auth: (props: unknown) => {
    supabaseMocks.authUiProps(props);
    return <div data-testid="supabase-auth">Mocked Auth</div>;
  }
}));

vi.mock('@stitches/core', () => ({
  createStitches: () => ({
    createTheme: vi.fn(),
    globalCss: vi.fn(),
    keyframes: vi.fn(),
    css: vi.fn()
  })
}));

vi.mock('@supabase/auth-ui-shared', () => ({
  ThemeSupa: {}
}));

// Mock window.location.reload
const mockReload = vi.fn();
Object.defineProperty(window, 'location', {
  value: { href: 'http://localhost/', origin: 'http://localhost', reload: mockReload },
  writable: true
});

function renderUserAuthUI(props?: React.ComponentProps<typeof UserAuthUI>) {
  return render(
    <UserPreferencesProvider>
      <UserAuthUI {...props} />
    </UserPreferencesProvider>,
  );
}

describe('UserAuthUI Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: null, isInitialized: false });
    supabaseMocks.insertFeedback.mockResolvedValue({ error: null });
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    document.documentElement.removeAttribute('data-interface-theme');
    document.documentElement.removeAttribute('data-interface-theme-choice');
    document.documentElement.lang = 'en';
  });

  it('shows login button when not authenticated', async () => {
    renderUserAuthUI();
    expect(screen.getByText('登入 / 註冊')).toBeInTheDocument();
  });

  it('uses English by default without offering language selection before sign-in', async () => {
    window.localStorage.removeItem('areqa:interface-language');
    renderUserAuthUI();

    expect(screen.getByText('Log in / Sign up')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Language' })).not.toBeInTheDocument();
    expect(document.documentElement.lang).toBe('en');

    fireEvent.click(screen.getByText('Log in / Sign up'));
    expect(screen.queryByRole('group', { name: 'Language' })).not.toBeInTheDocument();
    expect(supabaseMocks.authUiProps.mock.lastCall?.[0]).toHaveProperty('localization', { variables: {} });
    expect(window.localStorage.getItem('areqa:interface-language')).toBeNull();
  });

  it('keeps a language explicitly selected earlier without a guest selector', async () => {
    renderUserAuthUI();

    expect(screen.getByText('登入 / 註冊')).toBeInTheDocument();
    fireEvent.click(screen.getByText('登入 / 註冊'));
    expect(screen.queryByRole('group', { name: '語言' })).not.toBeInTheDocument();
    expect(supabaseMocks.authUiProps.mock.lastCall?.[0]).toHaveProperty(
      'localization.variables.sign_in.button_label', '登入',
    );
  });

  it('updates the user display on SIGNED_IN event', async () => {
    window.localStorage.removeItem('areqa:interface-language');
    vi.mocked(supabase.auth.getUser).mockResolvedValueOnce({
      data: { user: { id: 'user_123', user_metadata: { username: 'testuser' } } } as any,
      error: null,
    });
    renderUserAuthUI();
    
    // Simulate Supabase SIGNED_IN event
    const mockSession = { user: { id: 'user_123', user_metadata: { username: 'testuser' } } };
    
    // @ts-ignore
    await act(async () => {
      supabase._triggerAuthStateChange('SIGNED_IN', mockSession);
    });

    // After signed in, it should display username
    await waitFor(() => {
      expect(screen.getByText('testuser')).toBeInTheDocument();
      expect(document.documentElement.lang).toBe('en');
    });

  });

  it('signs out without deleting persisted history or reloading the page', async () => {
    // Start with logged in state
    vi.mocked(supabase.auth.getSession).mockResolvedValueOnce({
      data: { session: { user: { id: 'user_123', user_metadata: { username: 'testuser' } } } as any }
    });
    vi.mocked(supabase.auth.getUser).mockResolvedValueOnce({
      data: { user: { id: 'user_123', user_metadata: { username: 'testuser' } } } as any,
      error: null,
    });

    renderUserAuthUI();

    // Wait for user to be loaded
    await waitFor(() => {
      expect(screen.getByText('testuser')).toBeInTheDocument();
    });

    // Click the user dropdown trigger (Antd dropdown needs to be clicked)
    fireEvent.click(screen.getByText('testuser'));

    // Wait for Dropdown menu to open and find '登出'
    const logoutBtn = await screen.findByText('登出');
    fireEvent.click(logoutBtn);

    // Verify logout chain
    await waitFor(() => {
      expect(supabase.auth.signOut).toHaveBeenCalledOnce();
      expect(mockReload).not.toHaveBeenCalled();
    });
    await act(async () => {
      // @ts-ignore - test-only auth event helper exposed by the Supabase mock.
      supabase._triggerAuthStateChange('SIGNED_OUT', null);
    });
    expect(screen.getByText('登入 / 註冊')).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('zh-TW');
    expect(window.localStorage.getItem('areqa:interface-language')).toBe('zh-TW');
  });

  it('submits contact feedback from the account dropdown', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValueOnce({
      data: { session: { user: { id: 'user_123', email: 'test@example.com', user_metadata: { username: 'testuser' } } } as any }
    });
    vi.mocked(supabase.auth.getUser).mockResolvedValueOnce({
      data: { user: { id: 'user_123', email: 'test@example.com', user_metadata: { username: 'testuser' } } } as any,
      error: null,
    });

    renderUserAuthUI();

    await waitFor(() => {
      expect(screen.getByText('testuser')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('testuser'));
    fireEvent.click(await screen.findByText('聯繫我們/意見回饋'));
    fireEvent.change(await screen.findByPlaceholderText('請輸入你的問題、建議或遇到的狀況...'), {
      target: { value: '希望可以加入問題回報分類。' },
    });
    fireEvent.click(screen.getByRole('button', { name: /送\s*出/ }));

    await waitFor(() => {
      expect(supabase.from).toHaveBeenCalledWith('feedback_submissions');
      expect(supabaseMocks.insertFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          user_id: 'user_123',
          email: 'test@example.com',
          display_name: 'testuser',
          content: '希望可以加入問題回報分類。',
        }),
      );
    });
  });

  it('updates and persists interface theme and language from the account dropdown', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValueOnce({
      data: { session: { user: { id: 'user_123', user_metadata: { username: 'testuser' } } } as any }
    });
    vi.mocked(supabase.auth.getUser).mockResolvedValueOnce({
      data: { user: { id: 'user_123', user_metadata: { username: 'testuser' } } } as any,
      error: null,
    });

    renderUserAuthUI();

    await waitFor(() => {
      expect(screen.getByText('testuser')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('testuser'));

    fireEvent.click(await screen.findByRole('button', { name: /介面外觀/ }));
    fireEvent.click(await screen.findByRole('button', { name: '明亮' }));
    fireEvent.click(screen.getByRole('button', { name: /語言/ }));
    fireEvent.click(screen.getByRole('button', { name: 'English' }));

    await waitFor(() => {
      expect(window.localStorage.getItem('areqa:interface-theme')).toBe('light');
      expect(window.localStorage.getItem('areqa:interface-language')).toBe('en');
      expect(document.documentElement.dataset.interfaceTheme).toBe('light');
      expect(document.documentElement.dataset.interfaceThemeChoice).toBe('light');
      expect(document.documentElement.lang).toBe('en');
    });
  });
});
