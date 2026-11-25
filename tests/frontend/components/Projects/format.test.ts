import { describe, expect, it } from 'vitest';
import { formatProjectTime } from '@/components/Projects/format';

const NOW = Date.parse('2026-11-25T12:00:00Z');

describe('formatProjectTime', () => {
  it('is empty without a date', () => {
    expect(formatProjectTime(null, 'en', NOW)).toBe('');
  });

  it('uses relative time inside a week and rounds sub-minute times up to one minute', () => {
    expect(formatProjectTime(new Date(NOW - 10_000), 'en', NOW)).toBe('1 minute ago');
    expect(formatProjectTime(new Date(NOW - 6 * 60_000), 'en', NOW)).toBe('6 minutes ago');
    expect(formatProjectTime(new Date(NOW - 3 * 3_600_000), 'en', NOW)).toBe('3 hours ago');
    expect(formatProjectTime(new Date(NOW - 3 * 86_400_000), 'en', NOW)).toBe('3 days ago');
    expect(formatProjectTime(new Date(NOW - 6 * 60_000), 'zh-TW', NOW)).toBe('6 分鐘前');
  });

  it('switches to a calendar date after a week and for future dates', () => {
    expect(formatProjectTime(new Date('2025-12-09T00:00:00Z'), 'en', NOW)).toMatch(/2025/);
    expect(formatProjectTime(new Date(NOW + 86_400_000), 'en', NOW)).toMatch(/2026/);
  });
});
