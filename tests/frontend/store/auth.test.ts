import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/store/auth';
import { supabase } from '@/lib/supabase';

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getUser: vi.fn(),
      getSession: vi.fn(),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  },
}));

describe('Auth Store session validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: null, isInitialized: false, lastValidatedAt: null });
    vi.mocked(supabase.auth.signOut).mockResolvedValue({ error: null } as never);
  });

  it('accepts the current server-confirmed user', async () => {
    const user = { id: 'user-1' } as never;
    vi.mocked(supabase.auth.getUser).mockResolvedValue({ data: { user }, error: null } as never);

    await expect(useAuthStore.getState().validateSession()).resolves.toBe(true);

    expect(useAuthStore.getState().user).toBe(user);
    expect(useAuthStore.getState().lastValidatedAt).toEqual(expect.any(Number));
    expect(supabase.auth.signOut).not.toHaveBeenCalled();
  });

  it('signs out locally when the server no longer recognizes the user', async () => {
    useAuthStore.setState({ user: { id: 'deleted-user' } as never });
    vi.mocked(supabase.auth.getUser).mockResolvedValue({
      data: { user: null },
      error: { status: 401, name: 'AuthApiError' },
    } as never);

    await expect(useAuthStore.getState().validateSession()).resolves.toBe(false);

    expect(supabase.auth.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('keeps the session during a transient validation network error', async () => {
    const user = { id: 'user-1' } as never;
    useAuthStore.setState({ user });
    vi.mocked(supabase.auth.getUser).mockResolvedValue({
      data: { user: null },
      error: { status: 0, name: 'FetchError' },
    } as never);

    await expect(useAuthStore.getState().validateSession()).resolves.toBe(false);

    expect(supabase.auth.signOut).not.toHaveBeenCalled();
    expect(useAuthStore.getState().user).toBe(user);
  });
});
