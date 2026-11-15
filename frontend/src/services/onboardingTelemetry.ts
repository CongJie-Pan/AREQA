/**
 * Best-effort delivery of guided-tour progress to the backend log.
 *
 * Payloads hold fixed codes only (event, mode, step id, position, outcome);
 * the backend rejects anything else. Failures never affect the tour.
 */
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';

export interface OnboardingTelemetryEvent {
  event: 'started' | 'step_viewed' | 'finished';
  mode: 'full' | 'features';
  step: string;
  stepIndex: number;
  stepCount: number;
  outcome?: 'completed' | 'skipped';
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export function sendOnboardingEvent(payload: OnboardingTelemetryEvent): void {
  logger.info('onboarding_event', { component: 'onboarding', ...payload });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3000);
  const delivery = (async () => authenticatedFetch(`${BACKEND_URL}/api/v1/onboarding/event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event: payload.event,
      mode: payload.mode,
      step: payload.step,
      step_index: payload.stepIndex,
      step_count: payload.stepCount,
      ...(payload.outcome ? { outcome: payload.outcome } : {}),
    }),
    signal: controller.signal,
  }))();
  // Telemetry must never affect the tour, even if the transport misbehaves.
  void delivery.catch(() => {
    logger.warn('onboarding_event_delivery_failed', { component: 'onboarding', event: payload.event });
  }).finally(() => clearTimeout(timer));
}
