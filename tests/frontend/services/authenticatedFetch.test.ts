import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { getAuthToken } from '@/database/db';
import { useAuthStore } from '@/store/auth';

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      refreshSession: vi.fn(),
    },
  },
}));
import { supabase } from '@/lib/supabase';

vi.mock('@/database/db', () => ({
  getAuthToken: vi.fn(),
}));

vi.mock('@/store/auth', () => ({
  useAuthStore: {
    getState: vi.fn(),
  },
}));

describe('authenticatedFetch', () => {
  const invalidateSession = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getAuthToken).mockReturnValue('token-1');
    vi.mocked(useAuthStore.getState).mockReturnValue({ invalidateSession } as never);
    vi.mocked(supabase.auth.refreshSession).mockResolvedValue({
      data: { session: null },
      error: null,
    } as never);
    vi.stubGlobal('fetch', vi.fn());
  });

  it('adds the current token and retries once after a 401', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    vi.mocked(supabase.auth.refreshSession).mockResolvedValue({
      data: { session: { access_token: 'token-2' } },
      error: null,
    } as never);

    await authenticatedFetch('/api/protected', { headers: { 'Content-Type': 'application/json' } });

    expect(fetch).toHaveBeenCalledTimes(2);
    const retryHeaders = vi.mocked(fetch).mock.calls[1][1]?.headers as Headers;
    expect(retryHeaders.get('Authorization')).toBe('Bearer token-2');
    expect(invalidateSession).not.toHaveBeenCalled();
    expect(supabase.auth.refreshSession).toHaveBeenCalledOnce();
  });

  it('refreshes a token that is within the expiry safety window before fetching', async () => {
    const expiringToken = `header.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 30 }))}.signature`;
    vi.mocked(getAuthToken).mockReturnValue(expiringToken);
    vi.mocked(supabase.auth.refreshSession).mockResolvedValue({
      data: { session: { access_token: 'token-refreshed' } },
      error: null,
    } as never);
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 200 }));

    await authenticatedFetch('/api/protected');

    const requestHeaders = vi.mocked(fetch).mock.calls[0][1]?.headers as Headers;
    expect(requestHeaders.get('Authorization')).toBe('Bearer token-refreshed');
    expect(supabase.auth.refreshSession).toHaveBeenCalledOnce();
  });

  it('invalidates the session when refresh cannot recover a 401', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 401 }));

    await authenticatedFetch('/api/protected');

    expect(invalidateSession).toHaveBeenCalledOnce();
    expect(supabase.auth.refreshSession).toHaveBeenCalledOnce();
  });

  it('does not invalidate an anonymous request that receives 401', async () => {
    vi.mocked(getAuthToken).mockReturnValue(null);
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 401 }));

    await authenticatedFetch('/api/guest');

    expect(invalidateSession).not.toHaveBeenCalled();
  });
});
