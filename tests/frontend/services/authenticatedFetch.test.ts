import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { getAuthToken } from '@/database/db';
import { useAuthStore } from '@/store/auth';

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
    vi.stubGlobal('fetch', vi.fn());
  });

  it('adds the current token and invalidates the session on 401', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 401 }));

    await authenticatedFetch('/api/protected', { headers: { 'Content-Type': 'application/json' } });

    expect(fetch).toHaveBeenCalledWith('/api/protected', expect.objectContaining({
      headers: expect.any(Headers),
    }));
    const requestHeaders = vi.mocked(fetch).mock.calls[0][1]?.headers as Headers;
    expect(requestHeaders.get('Authorization')).toBe('Bearer token-1');
    expect(invalidateSession).toHaveBeenCalledOnce();
  });

  it('does not invalidate an anonymous request that receives 401', async () => {
    vi.mocked(getAuthToken).mockReturnValue(null);
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 401 }));

    await authenticatedFetch('/api/guest');

    expect(invalidateSession).not.toHaveBeenCalled();
  });
});
