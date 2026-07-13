import { getAuthToken } from '@/database/db';
import { supabase } from '@/lib/supabase';
import { useAuthStore } from '@/store/auth';

const TOKEN_REFRESH_SKEW_SECONDS = 60;
let refreshPromise: Promise<string | null> | null = null;

function getTokenExpiry(token: string): number | null {
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return typeof decoded.exp === 'number' ? decoded.exp : null;
  } catch {
    return null;
  }
}

function shouldRefresh(token: string): boolean {
  const expiry = getTokenExpiry(token);
  return expiry !== null && expiry <= Math.floor(Date.now() / 1000) + TOKEN_REFRESH_SKEW_SECONDS;
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const { data, error } = await supabase.auth.refreshSession();
        if (error) return null;
        return data.session?.access_token ?? null;
      } catch {
        return null;
      }
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function getRequestToken(): Promise<string | null> {
  const token = getAuthToken();
  if (!token || !shouldRefresh(token)) return token;
  return (await refreshAccessToken()) ?? token;
}

function withAuthorization(init: RequestInit, token: string | null): RequestInit {
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  else headers.delete('Authorization');
  return { ...init, headers };
}

/**
 * Fetch wrapper for backend endpoints that may receive an authenticated token.
 * Expiring sessions are refreshed once and a single 401 is retried once.
 */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  let token = await getRequestToken();
  let response = await fetch(input, withAuthorization(init, token));

  if (token && response.status === 401) {
    token = await refreshAccessToken();
    if (token) {
      response = await fetch(input, withAuthorization(init, token));
    }

    if (response.status === 401) {
      void useAuthStore.getState().invalidateSession();
    }
  }

  return response;
}
