'use client';

import type { ReactNode } from 'react';
import type { InterfacePreferences } from '@/lib/interfacePreferences';
import { ConfigProvider, theme, App } from 'antd';
import { StyleProvider } from 'antd-style';
import {
  UserPreferencesProvider,
  useUserPreferences,
} from '@/contexts/UserPreferencesContext';

interface AppProvidersProps {
  children: ReactNode;
  initialPreferences?: InterfacePreferences;
}

interface ThemedAppProvidersProps {
  children: ReactNode;
}

/**
 * Client-only UI providers for Ant Design and antd-style.
 *
 * Next App Router server layouts can render client components, but importing
 * antd-style's provider directly from a server module breaks production page
 * collection. Keeping these providers behind a client boundary preserves the
 * existing theme setup while allowing global critical CSS to cover first paint.
 */
export function AppProviders({ children, initialPreferences }: AppProvidersProps) {
  return (
    <StyleProvider hashPriority="high">
      <UserPreferencesProvider initialPreferences={initialPreferences}>
        <ThemedAppProviders>{children}</ThemedAppProviders>
      </UserPreferencesProvider>
    </StyleProvider>
  );
}

/**
 * Applies the persisted color preference to Ant Design components.
 *
 * Args:
 *   children: React subtree rendered inside Ant Design's App provider.
 *
 * Returns:
 *   The themed provider tree.
 */
function ThemedAppProviders({ children }: ThemedAppProvidersProps) {
  const { resolvedTheme } = useUserPreferences();
  const isDarkTheme = resolvedTheme === 'dark';

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkTheme ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#d8a25c',
          colorInfo: '#d8a25c',
          colorBgBase: isDarkTheme ? '#130f18' : '#f7f4ef',
          colorBgContainer: isDarkTheme ? '#1e1826' : '#ffffff',
          colorBgElevated: isDarkTheme ? '#1e1826' : '#ffffff',
          colorBgLayout: isDarkTheme ? '#130f18' : '#f7f4ef',
          colorTextBase: isDarkTheme ? '#f0f0f0' : '#1d1b20',
        },
      }}
    >
      <App>{children}</App>
    </ConfigProvider>
  );
}
