import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { UserAuthUI } from '@/components/Auth';
import { supabase } from '@/lib/supabase';

// Mock matchMedia for Ant Design Modal
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // Deprecated
    removeListener: vi.fn(), // Deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
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
  Auth: () => <div data-testid="supabase-auth">Mocked Auth</div>
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
  value: { reload: mockReload },
  writable: true
});

describe('UserAuthUI Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows login button when not authenticated', async () => {
    render(<UserAuthUI />);
    expect(screen.getByText('登入 / 註冊')).toBeInTheDocument();
  });

  it('updates the user display on SIGNED_IN event', async () => {
    vi.mocked(supabase.auth.getUser).mockResolvedValueOnce({
      data: { user: { id: 'user_123', user_metadata: { username: 'testuser' } } } as any,
      error: null,
    });
    render(<UserAuthUI />);
    
    // Simulate Supabase SIGNED_IN event
    const mockSession = { user: { id: 'user_123', user_metadata: { username: 'testuser' } } };
    
    // @ts-ignore
    await act(async () => {
      supabase._triggerAuthStateChange('SIGNED_IN', mockSession);
    });

    // After signed in, it should display username
    await waitFor(() => {
      expect(screen.getByText('testuser')).toBeInTheDocument();
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

    render(<UserAuthUI />);

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
  });
});
