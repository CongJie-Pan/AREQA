import { describe, expect, it } from 'vitest';
import { formatUserDate, parseServerDate } from '@/utils/dateTime';

describe('dateTime utilities', () => {
  it('treats timezone-less server timestamps as UTC', () => {
    expect(parseServerDate('2026-07-11T16:30:00').toISOString()).toBe('2026-07-11T16:30:00.000Z');
  });

  it('formats the same instant in the requested user timezone', () => {
    const timestamp = '2026-07-12T00:30:00Z';

    expect(formatUserDate(timestamp, { timeZone: 'Asia/Taipei', dateStyle: 'short' })).toBe('2026/7/12');
    expect(formatUserDate(timestamp, { timeZone: 'America/Los_Angeles', dateStyle: 'short' })).toBe('2026/7/11');
  });
});
