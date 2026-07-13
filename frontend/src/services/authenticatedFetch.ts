import { getAuthToken } from '@/database/db';
import { useAuthStore } from '@/store/auth';

/**
 * Fetch wrapper for backend endpoints that may receive an authenticated token.
 * A rejected authenticated request invalidates the local session immediately.
 */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init.headers);

  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(input, { ...init, headers });

  if (token && response.status === 401) {
    void useAuthStore.getState().invalidateSession();
  }

  return response;
}
