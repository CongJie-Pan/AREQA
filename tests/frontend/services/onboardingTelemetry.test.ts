import { describe, expect, it, vi } from 'vitest';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn(async () => new Response('{}')) }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { sendOnboardingEvent } from '@/services/onboardingTelemetry';

describe('sendOnboardingEvent', () => {
  it('posts only fixed tour codes to the backend', () => {
    sendOnboardingEvent({ event: 'finished', mode: 'features', step: 'replyMore', stepIndex: 2, stepCount: 4, outcome: 'skipped' });

    const [url, init] = vi.mocked(authenticatedFetch).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/onboarding\/event$/);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      event: 'finished', mode: 'features', step: 'replyMore', step_index: 2, step_count: 4, outcome: 'skipped',
    });
  });
});
