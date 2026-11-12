/** Validated UI preferences shared by server rendering and the browser bootstrap. */
export type InterfaceTheme = 'light' | 'dark' | 'system';
export type ResolvedInterfaceTheme = 'light' | 'dark';
export type InterfaceLanguage = 'zh-TW' | 'zh-CN' | 'en';
export interface InterfacePreferences {
  theme: InterfaceTheme;
  language: InterfaceLanguage;
}

export const DEFAULT_INTERFACE_PREFERENCES: InterfacePreferences = { theme: 'system', language: 'en' };
export const THEME_STORAGE_KEY = 'areqa:interface-theme';
export const LANGUAGE_STORAGE_KEY = 'areqa:interface-language';
export const THEME_COOKIE = 'areqa_interface_theme';
export const LANGUAGE_COOKIE = 'areqa_interface_language';
const THEMES = ['light', 'dark', 'system'] as const;
const LANGUAGES = ['zh-TW', 'zh-CN', 'en'] as const;

/** Sanitizes untrusted storage/cookie values against the supported preference lists. */
export function sanitizeInterfacePreferences(
  theme: unknown,
  language: unknown,
  fallback = DEFAULT_INTERFACE_PREFERENCES,
): InterfacePreferences {
  return {
    theme: THEMES.includes(theme as InterfaceTheme) ? theme as InterfaceTheme : fallback.theme,
    language: LANGUAGES.includes(language as InterfaceLanguage) ? language as InterfaceLanguage : fallback.language,
  };
}

/** Reads legacy localStorage preferences, falling back when browser storage is denied. */
export function readBrowserPreferences(fallback = DEFAULT_INTERFACE_PREFERENCES): InterfacePreferences {
  if (typeof window === 'undefined') return fallback;
  try {
    return sanitizeInterfacePreferences(
      window.localStorage.getItem(THEME_STORAGE_KEY),
      window.localStorage.getItem(LANGUAGE_STORAGE_KEY),
      fallback,
    );
  } catch {
    return fallback;
  }
}

/** Mirrors only validated UI choices into cookies so later requests can render them. */
export function writePreferenceCookies(preferences: InterfacePreferences): void {
  const { theme, language } = sanitizeInterfacePreferences(preferences.theme, preferences.language);
  try {
    document.cookie = `${THEME_COOKIE}=${theme}; Path=/; Max-Age=31536000; SameSite=Lax`;
    document.cookie = `${LANGUAGE_COOKIE}=${language}; Path=/; Max-Age=31536000; SameSite=Lax`;
  } catch {
    // Cookie persistence is optional; local state and legacy storage still work.
  }
}

/**
 * Builds the blocking head script that applies the theme before the first paint.
 *
 * Args:
 *   initial: Server-validated cookie snapshot used when localStorage is unavailable.
 * Returns:
 *   A self-contained script containing only allowlisted UI values and fixed keys.
 * Side effects:
 *   The browser script sets root attributes and migrates legacy choices to cookies.
 *   React still hydrates from the server snapshot, never from these DOM mutations.
 */
export function createPreferenceBootstrap(initial: InterfacePreferences): string {
  const safe = sanitizeInterfacePreferences(initial.theme, initial.language);
  return `(()=>{
    let p=${JSON.stringify(safe)};
    try {
      const t=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
      const l=localStorage.getItem(${JSON.stringify(LANGUAGE_STORAGE_KEY)});
      if(${JSON.stringify(THEMES)}.includes(t)) p.theme=t;
      if(${JSON.stringify(LANGUAGES)}.includes(l)) p.language=l;
    } catch {}
    let dark=true;
    try { dark=matchMedia('(prefers-color-scheme: dark)').matches; } catch {}
    const root=document.documentElement;
    root.dataset.interfaceTheme=p.theme==='system'?(dark?'dark':'light'):p.theme;
    root.dataset.interfaceThemeChoice=p.theme;
    root.lang=p.language;
    try {
      document.cookie=${JSON.stringify(THEME_COOKIE + '=')}+p.theme+'; Path=/; Max-Age=31536000; SameSite=Lax';
      document.cookie=${JSON.stringify(LANGUAGE_COOKIE + '=')}+p.language+'; Path=/; Max-Age=31536000; SameSite=Lax';
    } catch {}
  })();`;
}
