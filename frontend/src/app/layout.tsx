import type { Metadata, Viewport } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { cookies } from 'next/headers';
import { createPreferenceBootstrap, sanitizeInterfacePreferences, THEME_COOKIE, LANGUAGE_COOKIE } from '@/lib/interfacePreferences';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { AppProviders } from './providers';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { PwaInstallPrompt } from '@/components/PwaInstallPrompt';
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
    apple: '/icon/areqa_icon_v4_192.png',
  },
};

export const viewport: Viewport = {
  viewportFit: 'cover',
  themeColor: '#d8a25c',
};

/**
 * Renders the request's validated UI preference snapshot and pre-paint bootstrap.
 * Reading cookies makes this layout request-specific, preventing shared theme HTML.
 */
export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const initialPreferences = sanitizeInterfacePreferences(
    cookieStore.get(THEME_COOKIE)?.value,
    cookieStore.get(LANGUAGE_COOKIE)?.value,
  );
  return (
    <html lang={initialPreferences.language} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: createPreferenceBootstrap(initialPreferences) }} />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ErrorBoundary>
          <AntdRegistry>
            <AppProviders initialPreferences={initialPreferences}>
              {children}
              <PwaInstallPrompt />
            </AppProviders>
          </AntdRegistry>
        </ErrorBoundary>
      </body>
    </html>
  );
}
