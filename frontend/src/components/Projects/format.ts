import type { InterfaceLanguage } from '@/contexts/UserPreferencesContext';

const LOCALES: Record<InterfaceLanguage, string> = { 'zh-TW': 'zh-TW', 'zh-CN': 'zh-CN', en: 'en' };
const DAY_MS = 86_400_000;

/** "6 分鐘前" / "3 days ago" within a week, otherwise a calendar date. */
export function formatProjectTime(value: Date | null | undefined, language: InterfaceLanguage, now = Date.now()): string {
  if (!value) return '';
  const locale = LOCALES[language] ?? 'en';
  const elapsed = now - value.getTime();
  if (elapsed >= 0 && elapsed < 7 * DAY_MS) {
    const format = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
    const minutes = Math.round(elapsed / 60_000);
    if (minutes < 60) return format.format(-Math.max(minutes, 1), 'minute');
    const hours = Math.round(minutes / 60);
    if (hours < 24) return format.format(-hours, 'hour');
    return format.format(-Math.round(hours / 24), 'day');
  }
  return new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'short', day: 'numeric' }).format(value);
}
