import type { Metadata, Viewport } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { AppProviders } from './providers';
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
    icon: '/logo/areqa_icon_v4_icoFile.ico',
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
            <AppProviders>
              <PwaLaunchScreen />
              {children}
              <PwaInstallPrompt />
            </AppProviders>
          </AntdRegistry>
        </ErrorBoundary>
      </body>
    </html>
  );
}
