/**
 * Shared runtime feature flag types for browser-visible AREQA features.
 *
 * These flags are sourced from the backend `/api/v1/features` endpoint at
 * runtime so toggling them requires changing backend settings only. The
 * frontend still fails closed until a valid backend response arrives.
 */

export interface RuntimeFeatureFlags {
  conversationHistoryDebugLogs: boolean;
}

export const disabledRuntimeFeatureFlags: RuntimeFeatureFlags = {
  conversationHistoryDebugLogs: false,
};

export function normalizeRuntimeFeatureFlags(payload: unknown): RuntimeFeatureFlags {
  const source = payload && typeof payload === 'object'
    ? payload as Record<string, unknown>
    : {};

  return {
    conversationHistoryDebugLogs: source.conversationHistoryDebugLogs === true,
  };
}
