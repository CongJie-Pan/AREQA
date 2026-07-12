export type DateTimeInput = string | number | Date;

/**
 * Parse server timestamps consistently. ISO strings without an explicit offset
 * are treated as UTC because backend timestamps represent UTC instants.
 */
export function parseServerDate(value: DateTimeInput): Date {
  if (value instanceof Date) return value;

  if (typeof value === 'number') {
    return new Date(value);
  }

  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasTimezone ? value : `${value}Z`);
}

/** Return the timezone configured by the user's browser. */
export function getUserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function formatUserDate(
  value: DateTimeInput,
  options: Intl.DateTimeFormatOptions = {},
): string {
  return new Intl.DateTimeFormat('zh-TW', {
    timeZone: getUserTimeZone(),
    ...options,
  }).format(parseServerDate(value));
}
