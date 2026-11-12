import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createPreferenceBootstrap,
  sanitizeInterfacePreferences,
  THEME_COOKIE,
  LANGUAGE_COOKIE,
} from '@/lib/interfacePreferences';

describe('pre-paint interface preference bootstrap', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-interface-theme');
  });

  function boot(theme: unknown, language: unknown, denied = false, prefersDark = false) {
    const script = createPreferenceBootstrap(sanitizeInterfacePreferences(theme, language));
    const storage = denied ? { getItem: () => { throw new Error('denied'); } } : localStorage;
    new Function('document', 'localStorage', 'matchMedia', script)(
      document, storage, vi.fn(() => ({ matches: prefersDark })),
    );
    return script;
  }

  it('applies a legacy light theme before React and mirrors language into SSR cookies', () => {
    localStorage.setItem('areqa:interface-theme', 'light');
    localStorage.setItem('areqa:interface-language', 'zh-TW');
    boot('system', 'en');
    expect(document.documentElement.dataset.interfaceTheme).toBe('light');
    expect(document.documentElement.lang).toBe('zh-TW');
    expect(document.cookie).toContain(`${THEME_COOKIE}=light`);
    expect(document.cookie).toContain(`${LANGUAGE_COOKIE}=zh-TW`);
  });

  it('uses the validated server cookie snapshot when localStorage is unavailable', () => {
    boot('light', 'zh-CN', true);
    expect(document.documentElement.dataset.interfaceTheme).toBe('light');
    expect(document.documentElement.lang).toBe('zh-CN');
  });

  it.each([true, false])('resolves the system theme before hydration (dark=%s)', (prefersDark) => {
    boot('system', 'en', false, prefersDark);
    expect(document.documentElement.dataset.interfaceTheme).toBe(prefersDark ? 'dark' : 'light');
    expect(document.documentElement.dataset.interfaceThemeChoice).toBe('system');
  });

  it('rejects unsupported values instead of interpolating cookie or storage content into script', () => {
    localStorage.setItem('areqa:interface-theme', 'invalid');
    localStorage.setItem('areqa:interface-language', 'invalid');
    const script = boot('</script><script>alert(1)</script>', 'invalid');
    expect(script).not.toContain('</script>');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dataset.interfaceThemeChoice).toBe('system');
  });
});
