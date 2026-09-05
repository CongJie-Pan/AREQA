/**
 * Authentication store
 * Keeps the Supabase session state in one place so data loading can be gated
 * until authentication has been resolved.
 */

import { create } from 'zustand';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';

interface AuthState {
  user: User | null;
  isInitialized: boolean;
  lastValidatedAt: number | null;
}

interface AuthActions {
  initialize: () => Promise<void>;
  validateSession: () => Promise<boolean>;
  invalidateSession: () => Promise<void>;
}

export type AuthStore = AuthState & AuthActions;

let initializationPromise: Promise<void> | null = null;
let unsubscribe: (() => void) | null = null;
let validationPromise: Promise<boolean> | null = null;
let invalidationPromise: Promise<void> | null = null;
const AUTH_REQUEST_TIMEOUT_MS = 8000;

function withTimeout<T>(operation: PromiseLike<T>, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = globalThis.setTimeout(() => {
      reject(new Error(`${label} timed out`));
    }, AUTH_REQUEST_TIMEOUT_MS);

    Promise.resolve(operation)
      .then(resolve, reject)
      .finally(() => {
        globalThis.clearTimeout(timeoutId);
      });
  });
}

const applySession = (session: Session | null) => {
  useAuthStore.setState({
    user: session?.user ?? null,
    isInitialized: true,
  });
};

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isInitialized: false,
  lastValidatedAt: null,

  initialize: async () => {
    if (initializationPromise) return initializationPromise;

    initializationPromise = (async () => {
      unsubscribe?.();
      let hasReceivedAuthEvent = false;
      const {
        data: { subscription },
      } = supabase.auth.onAuthStateChange((_event, session) => {
        hasReceivedAuthEvent = true;
        applySession(session);
      });
      unsubscribe = () => subscription.unsubscribe();

      const { data, error } = await withTimeout(supabase.auth.getSession(), 'Supabase session lookup');
      if (error && !hasReceivedAuthEvent) {
        set({ user: null, isInitialized: true, lastValidatedAt: Date.now() });
      } else if (!hasReceivedAuthEvent && data.session?.user) {
        set({ user: data.session.user, isInitialized: true });
      }

      await useAuthStore.getState().validateSession();
    })().catch((error) => {
      console.warn('Failed to initialize Supabase auth:', error instanceof Error ? error.message : error);
      set({ user: null, isInitialized: true, lastValidatedAt: Date.now() });
    }).finally(() => {
      const current = useAuthStore.getState();
      if (!current.isInitialized) {
        set({ user: null, isInitialized: true, lastValidatedAt: Date.now() });
      }
      initializationPromise = null;
    });

    return initializationPromise;
  },

  validateSession: async () => {
    if (validationPromise) return validationPromise;

    validationPromise = (async () => {
      let data: { user: User | null } = { user: null };
      let error: { status?: number; name?: string } | null = null;

      try {
        const result = await withTimeout(supabase.auth.getUser(), 'Supabase user validation');
        data = result.data;
        error = result.error;
      } catch (caughtError) {
        error = caughtError as { status?: number; name?: string };
      }

      const status = (error as { status?: number } | null)?.status;
      const errorName = (error as { name?: string } | null)?.name;

      if (data.user) {
        set({ user: data.user, isInitialized: true, lastValidatedAt: Date.now() });
        return true;
      }

      const sessionIsInvalid =
        status === 400 ||
        status === 401 ||
        status === 403 ||
        status === 404 ||
        errorName === 'AuthSessionMissingError' ||
        !error;

      if (sessionIsInvalid || !useAuthStore.getState().user) {
        await useAuthStore.getState().invalidateSession();
      }

      return false;
    })().finally(() => {
      validationPromise = null;
    });

    return validationPromise;
  },

  invalidateSession: async () => {
    if (invalidationPromise) return invalidationPromise;

    invalidationPromise = (async () => {
      set({ user: null, isInitialized: true, lastValidatedAt: Date.now() });
      try {
        const { error } = await withTimeout(
          supabase.auth.signOut({ scope: 'local' }),
          'Supabase local sign out',
        );
        if (error) {
          // Local state is already cleared; a stale local token must not keep the UI authenticated.
          console.warn('Failed to remove the local Supabase session:', error.message);
        }
      } catch (error) {
        console.warn('Failed to remove the local Supabase session:', error instanceof Error ? error.message : error);
      }
    })().finally(() => {
      invalidationPromise = null;
    });

    return invalidationPromise;
  },
}));

export async function initializeAuth(): Promise<void> {
  return useAuthStore.getState().initialize();
}
