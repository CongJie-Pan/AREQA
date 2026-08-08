'use client';

import type { ReactNode } from 'react';
import { ConfigProvider, theme, App } from 'antd';
import { StyleProvider } from 'antd-style';

interface AppProvidersProps {
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
export function AppProviders({ children }: AppProvidersProps) {
  return (
    <StyleProvider hashPriority="high">
      <ConfigProvider
        theme={{
          algorithm: theme.darkAlgorithm,
          token: {
            colorPrimary: '#d8a25c',
            colorInfo: '#d8a25c',
            colorBgBase: '#130f18',
            colorBgContainer: '#1e1826',
            colorBgElevated: '#1e1826',
            colorBgLayout: '#130f18',
            colorTextBase: '#f0f0f0',
          },
        }}
      >
        <App>{children}</App>
      </ConfigProvider>
    </StyleProvider>
  );
}

