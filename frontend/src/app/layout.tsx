import type { Metadata, Viewport } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { ConfigProvider, theme, App } from 'antd';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { PwaInstallPrompt } from '@/components/PwaInstallPrompt';
import { PwaLaunchScreen } from '@/components/PwaLaunchScreen';
import './globals.css';
import 'katex/dist/katex.min.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'AREQA',
  applicationName: 'AREQA',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'AREQA',
  },
  description: '結合思考過程視覺化的 Adaptive RAG 教育問答系統',
  icons: {
    icon: '/logo/favicon.ico',
    apple: '/icon/areqa_icon_v3_full_Fill_512.png',
  },
};

export const viewport: Viewport = {
  themeColor: '#d8a25c',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ErrorBoundary>
          <AntdRegistry>
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
              <App>
                <PwaLaunchScreen />
                {children}
                <PwaInstallPrompt />
              </App>
            </ConfigProvider>
          </AntdRegistry>
        </ErrorBoundary>
      </body>
    </html>
  );
}
