/**
 * Shared runtime feature flag types for browser-visible AREQA features.
 *
 * These flags are sourced from the backend `/api/v1/features` endpoint at
 * runtime so reopening archived product surfaces requires changing backend
 * settings only. The frontend still fails closed until a valid backend response
 * arrives.
 */

export interface RuntimeFeatureFlags {
  mailbox: boolean;
  compeer: boolean;
  compeerTelemetry: boolean;
  conversationHistoryDebugLogs: boolean;
}

export const disabledRuntimeFeatureFlags: RuntimeFeatureFlags = {
  mailbox: false,
  compeer: false,
  compeerTelemetry: false,
  conversationHistoryDebugLogs: false,
};

export function normalizeRuntimeFeatureFlags(payload: unknown): RuntimeFeatureFlags {
  const source = payload && typeof payload === 'object'
    ? payload as Record<string, unknown>
    : {};
  const compeer = source.compeer === true;

  return {
    mailbox: source.mailbox === true,
    compeer,
    compeerTelemetry: compeer && source.compeerTelemetry === true,
    conversationHistoryDebugLogs: source.conversationHistoryDebugLogs === true,
  };
}
