import { create } from 'zustand';
import {
  disabledRuntimeFeatureFlags,
  normalizeRuntimeFeatureFlags,
  RuntimeFeatureFlags,
} from '@/config/features';
import { logger } from '@/utils/logger';

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

interface FeatureState extends RuntimeFeatureFlags {
  initialized: boolean;
  loading: boolean;
  error: string | null;
  fetchFeatures: () => Promise<void>;
}

/**
 * Runtime feature store sourced from the backend settings endpoint.
 *
 * The store fails closed until `/api/v1/features` returns a valid payload. This
 * keeps archived UI surfaces hidden during startup, network failures, and
 * incompatible backend deployments.
 */
export const useFeatureStore = create<FeatureState>((set, get) => ({
  ...disabledRuntimeFeatureFlags,
  initialized: false,
  loading: false,
  error: null,

  fetchFeatures: async () => {
    const state = get();
    if (state.loading || state.initialized) {
      return;
    }

    set({ loading: true, error: null });
    try {
      const response = await fetch(`${backendUrl}/api/v1/features`, {
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(`Feature endpoint returned ${response.status}`);
      }

      const flags = normalizeRuntimeFeatureFlags(await response.json());
      set({
        ...flags,
        initialized: true,
        loading: false,
        error: null,
      });
      logger.info('features.runtime_loaded', {
        mailbox: flags.mailbox,
        compeer: flags.compeer,
        compeerTelemetry: flags.compeerTelemetry,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        ...disabledRuntimeFeatureFlags,
        initialized: true,
        loading: false,
        error: message,
      });
      logger.warn('features.runtime_load_failed', { reason: message });
    }
  },
}));
