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
}

interface AuthActions {
  initialize: () => Promise<void>;
}

export type AuthStore = AuthState & AuthActions;

let initializationPromise: Promise<void> | null = null;
let unsubscribe: (() => void) | null = null;

const applySession = (session: Session | null) => {
  useAuthStore.setState({
    user: session?.user ?? null,
    isInitialized: true,
  });
};

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isInitialized: false,

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

      const { data, error } = await supabase.auth.getSession();
      if (!hasReceivedAuthEvent) {
        if (error) {
          set({ user: null, isInitialized: true });
        } else {
          applySession(data.session);
        }
      }
    })().finally(() => {
      initializationPromise = null;
    });

    return initializationPromise;
  },
}));

export async function initializeAuth(): Promise<void> {
  return useAuthStore.getState().initialize();
}
