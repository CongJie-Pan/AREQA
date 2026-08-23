'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type InterfaceTheme = 'light' | 'dark' | 'system';
export type ResolvedInterfaceTheme = 'light' | 'dark';
export type InterfaceLanguage = 'zh-TW' | 'zh-CN' | 'en';

interface UserPreferencesContextValue {
  theme: InterfaceTheme;
  resolvedTheme: ResolvedInterfaceTheme;
  language: InterfaceLanguage;
  setTheme: (theme: InterfaceTheme) => void;
  setLanguage: (language: InterfaceLanguage) => void;
}

interface UserPreferencesProviderProps {
  children: ReactNode;
}

const THEME_STORAGE_KEY = 'areqa:interface-theme';
const LANGUAGE_STORAGE_KEY = 'areqa:interface-language';
const SYSTEM_DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)';

const SUPPORTED_THEMES: readonly InterfaceTheme[] = ['light', 'dark', 'system'];
const SUPPORTED_LANGUAGES: readonly InterfaceLanguage[] = ['zh-TW', 'zh-CN', 'en'];

const defaultPreferences: UserPreferencesContextValue = {
  theme: 'system',
  resolvedTheme: 'dark',
  language: 'zh-TW',
  setTheme: () => undefined,
  setLanguage: () => undefined,
};

const UserPreferencesContext = createContext<UserPreferencesContextValue>(defaultPreferences);

/**
 * Checks whether a stored value is one of the supported interface themes.
 *
 * Args:
 *   value: Unknown value read from browser storage.
 *
 * Returns:
 *   True when the value can be safely used as an InterfaceTheme.
 */
function isInterfaceTheme(value: unknown): value is InterfaceTheme {
  return typeof value === 'string' && SUPPORTED_THEMES.includes(value as InterfaceTheme);
}

/**
 * Checks whether a stored value is one of the supported interface languages.
 *
 * Args:
 *   value: Unknown value read from browser storage.
 *
 * Returns:
 *   True when the value can be safely used as an InterfaceLanguage.
 */
function isInterfaceLanguage(value: unknown): value is InterfaceLanguage {
  return typeof value === 'string' && SUPPORTED_LANGUAGES.includes(value as InterfaceLanguage);
}

/**
 * Resolves the effective color theme for the current browser environment.
 *
 * Args:
 *   selectedTheme: User-selected theme mode.
 *   prefersDark: Current operating-system dark-mode preference.
 *
 * Returns:
 *   The concrete light or dark theme that should be applied to the UI.
 */
function resolveInterfaceTheme(
  selectedTheme: InterfaceTheme,
  prefersDark: boolean,
): ResolvedInterfaceTheme {
  if (selectedTheme === 'system') {
    return prefersDark ? 'dark' : 'light';
  }

  return selectedTheme;
}

/**
 * Reads persisted preferences without trusting arbitrary localStorage values.
 *
 * Returns:
 *   Sanitized preference values with safe defaults.
 *
 * Side effects:
 *   Reads localStorage when running in a browser.
 */
function readStoredPreferences(): Pick<UserPreferencesContextValue, 'theme' | 'language'> {
  if (typeof window === 'undefined') {
    return { theme: defaultPreferences.theme, language: defaultPreferences.language };
  }

  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    const storedLanguage = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);

    return {
      theme: isInterfaceTheme(storedTheme) ? storedTheme : defaultPreferences.theme,
      language: isInterfaceLanguage(storedLanguage) ? storedLanguage : defaultPreferences.language,
    };
  } catch {
    // Browser privacy modes can deny storage access. Falling back keeps the app usable.
    return { theme: defaultPreferences.theme, language: defaultPreferences.language };
  }
}

/**
 * Reads the current system color preference.
 *
 * Returns:
 *   True when the browser currently prefers dark mode.
 *
 * Side effects:
 *   Reads matchMedia when running in a browser.
 */
function readSystemPrefersDark(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }

  try {
    return window.matchMedia(SYSTEM_DARK_MEDIA_QUERY).matches;
  } catch {
    return true;
  }
}

/**
 * Stores a user preference while keeping storage failures non-fatal.
 *
 * Args:
 *   key: localStorage key owned by the preferences module.
 *   value: Sanitized preference value.
 *
 * Side effects:
 *   Writes localStorage when available.
 */
function persistPreference(key: string, value: string): void {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Preference persistence is best-effort and must never block the chat UI.
  }
}

/**
 * Provides persisted user interface preferences to client components.
 *
 * Args:
 *   children: React subtree that can read and update preferences.
 *
 * Side effects:
 *   Persists preference changes, listens to system theme changes, and writes
 *   `data-interface-theme`, `data-interface-theme-choice`, and `lang` on the
 *   root document element for CSS and browser language integration.
 */
export function UserPreferencesProvider({ children }: UserPreferencesProviderProps) {
  const [theme, setThemeState] = useState<InterfaceTheme>(() => readStoredPreferences().theme);
  const [language, setLanguageState] = useState<InterfaceLanguage>(
    () => readStoredPreferences().language,
  );
  const [prefersDark, setPrefersDark] = useState(readSystemPrefersDark);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQueryList = window.matchMedia(SYSTEM_DARK_MEDIA_QUERY);
    const handleSystemThemeChange = (event: MediaQueryListEvent) => {
      setPrefersDark(event.matches);
    };

    mediaQueryList.addEventListener?.('change', handleSystemThemeChange);

    return () => {
      mediaQueryList.removeEventListener?.('change', handleSystemThemeChange);
    };
  }, []);

  const resolvedTheme = useMemo(
    () => resolveInterfaceTheme(theme, prefersDark),
    [prefersDark, theme],
  );

  useEffect(() => {
    if (typeof document === 'undefined') return;

    document.documentElement.dataset.interfaceTheme = resolvedTheme;
    document.documentElement.dataset.interfaceThemeChoice = theme;
    document.documentElement.lang = language;
  }, [language, resolvedTheme, theme]);

  const setTheme = useCallback((nextTheme: InterfaceTheme) => {
    setThemeState(nextTheme);
    persistPreference(THEME_STORAGE_KEY, nextTheme);
  }, []);

  const setLanguage = useCallback((nextLanguage: InterfaceLanguage) => {
    setLanguageState(nextLanguage);
    persistPreference(LANGUAGE_STORAGE_KEY, nextLanguage);
  }, []);

  const contextValue = useMemo<UserPreferencesContextValue>(
    () => ({
      theme,
      resolvedTheme,
      language,
      setTheme,
      setLanguage,
    }),
    [language, resolvedTheme, setLanguage, setTheme, theme],
  );

  return (
    <UserPreferencesContext.Provider value={contextValue}>
      {children}
    </UserPreferencesContext.Provider>
  );
}

/**
 * Returns the current persisted user interface preferences.
 *
 * Returns:
 *   Theme, resolved theme, language, and setter callbacks.
 */
export function useUserPreferences(): UserPreferencesContextValue {
  return useContext(UserPreferencesContext);
}
