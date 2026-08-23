/**
 * Centralized runtime feature flags for browser-visible AREQA features.
 *
 * The flags intentionally fail closed: a feature is visible or active only when
 * its public environment variable is exactly "true". This keeps archived
 * product surfaces in the codebase while preventing accidental exposure in
 * deployments that do not opt in.
 */

const isPublicFlagEnabled = (value: string | undefined): boolean => value === 'true';

export const isMailboxEnabled = (): boolean =>
  isPublicFlagEnabled(process.env.NEXT_PUBLIC_ENABLE_MAILBOX);

export const isCompeerEnabled = (): boolean =>
  isPublicFlagEnabled(process.env.NEXT_PUBLIC_ENABLE_COMPEER);

export const isCompeerTelemetryEnabled = (): boolean =>
  isCompeerEnabled() &&
  isPublicFlagEnabled(process.env.NEXT_PUBLIC_ENABLE_COMPEER_TELEMETRY);
