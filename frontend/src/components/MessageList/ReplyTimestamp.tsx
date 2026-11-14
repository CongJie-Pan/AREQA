'use client';

import { useSyncExternalStore } from 'react';
import { Tooltip } from 'antd';
import { APP_TIME_ZONE, parseServerDate, type DateTimeInput } from '@/utils/dateTime';
import type { InterfaceLanguage } from '@/lib/interfacePreferences';

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const listeners = new Set<() => void>();
let now = 0;
let timer: ReturnType<typeof setInterval> | undefined;

function tick() {
  now = Date.now();
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (timer === undefined) {
    tick();
    timer = setInterval(tick, MINUTE);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

const readClock = () => now;
const readServerClock = () => 0;

function relativeLabel(date: Date, clock: number, locale: string) {
  const elapsed = Math.max(0, clock - date.getTime());
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'always' });
  if (elapsed < HOUR) return formatter.format(-Math.floor(elapsed / MINUTE), 'minute');
  if (elapsed < DAY) return formatter.format(-Math.floor(elapsed / HOUR), 'hour');
  return formatter.format(-Math.floor(elapsed / DAY), 'day');
}

export function ReplyTimestamp({ value, language, className }: {
  value: DateTimeInput;
  language: InterfaceLanguage;
  className?: string;
}) {
  const clock = useSyncExternalStore(subscribe, readClock, readServerClock);
  const date = parseServerDate(value);
  if (!Number.isFinite(date.getTime())) return null;

  const options = { timeZone: APP_TIME_ZONE };
  const exact = new Intl.DateTimeFormat(language, { ...options, dateStyle: 'long', timeStyle: 'short' }).format(date);
  const elapsed = clock - date.getTime();
  const label = clock && elapsed >= -MINUTE && elapsed < 7 * DAY
    ? (elapsed < MINUTE
      ? ({ en: 'Just now', 'zh-TW': '剛剛', 'zh-CN': '刚刚' })[language]
      : relativeLabel(date, clock, language))
    : new Intl.DateTimeFormat(language, { ...options, month: 'short', day: 'numeric' }).format(date);

  return (
    <Tooltip title={exact} trigger={['hover', 'focus']}>
      <time dateTime={date.toISOString()} aria-label={exact} className={className} tabIndex={0}>
        {label}
      </time>
    </Tooltip>
  );
}
