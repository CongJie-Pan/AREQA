'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Typography } from 'antd';
import { createStyles } from 'antd-style';
import { Download, Share2, X } from 'lucide-react';

const { Text, Title } = Typography;

const DISMISS_UNTIL_KEY = 'areqa:pwa-install-dismissed-until';
const DISMISS_DURATION_MS = 7 * 24 * 60 * 60 * 1000;

type BeforeInstallPromptChoice = {
  outcome: 'accepted' | 'dismissed';
  platform: string;
};

type BeforeInstallPromptEvent = Event & {
  platforms?: string[];
  userChoice: Promise<BeforeInstallPromptChoice>;
  prompt: () => Promise<void>;
};

type PromptMode = 'native' | 'ios';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    position: fixed;
    left: 16px;
    right: 16px;
    bottom: calc(16px + env(safe-area-inset-bottom));
    z-index: 1100;
    display: none;
    padding: ${token.paddingMD}px;
    border: 1px solid rgba(216, 162, 92, 0.42);
    border-radius: ${token.borderRadiusLG}px;
    background: rgba(30, 24, 38, 0.96);
    color: ${token.colorTextBase};
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.38);
    backdrop-filter: blur(14px);

    @media (max-width: 768px) {
      display: block;
    }
  `,
  closeButton: css`
    position: absolute;
    top: 10px;
    right: 10px;
    width: 32px;
    height: 32px;
    min-width: 32px;
    color: ${token.colorTextSecondary};

    &.ant-btn:hover {
      color: ${token.colorTextBase} !important;
      background: rgba(255, 255, 255, 0.08) !important;
    }
  `,
  header: css`
    display: flex;
    gap: ${token.marginSM}px;
    padding-right: 34px;
  `,
  iconWrap: css`
    display: inline-flex;
    width: 40px;
    height: 40px;
    flex: 0 0 40px;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    background: rgba(216, 162, 92, 0.14);
    color: ${token.colorPrimary};
  `,
  title: css`
    &.ant-typography {
      margin: 0 0 ${token.marginXXS}px;
      color: ${token.colorTextBase};
      font-size: ${token.fontSizeLG}px;
      line-height: 1.25;
    }
  `,
  description: css`
    &.ant-typography {
      display: block;
      color: ${token.colorTextSecondary};
      font-size: ${token.fontSizeSM}px;
      line-height: 1.45;
    }
  `,
  actions: css`
    display: flex;
    gap: ${token.marginSM}px;
    margin-top: ${token.marginMD}px;
  `,
  installButton: css`
    flex: 1;
    height: 42px;
    border: 0;
    background: ${token.colorPrimary};
    color: #130f18;
    font-weight: 700;

    &.ant-btn:hover,
    &.ant-btn:focus-visible {
      background: #e1b16f !important;
      color: #130f18 !important;
    }
  `,
  laterButton: css`
    height: 42px;
    color: ${token.colorTextSecondary};
    border-color: rgba(255, 255, 255, 0.14);
    background: rgba(255, 255, 255, 0.04);

    &.ant-btn:hover {
      color: ${token.colorTextBase} !important;
      border-color: rgba(255, 255, 255, 0.24) !important;
      background: rgba(255, 255, 255, 0.08) !important;
    }
  `,
}));

function getDismissedUntil(): number {
  const rawValue = window.localStorage.getItem(DISMISS_UNTIL_KEY);
  const dismissedUntil = rawValue ? Number(rawValue) : 0;

  return Number.isFinite(dismissedUntil) ? dismissedUntil : 0;
}

function isStandaloneDisplay(): boolean {
  const navigatorWithStandalone = navigator as Navigator & {
    standalone?: boolean;
    maxTouchPoints?: number;
  };

  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    navigatorWithStandalone.standalone === true
  );
}

function isMobileViewport(): boolean {
  return window.matchMedia('(max-width: 768px)').matches;
}

function isIOSDevice(): boolean {
  const navigatorWithTouchPoints = navigator as Navigator & {
    maxTouchPoints?: number;
  };
  const userAgent = navigator.userAgent;

  return (
    /iphone|ipad|ipod/i.test(userAgent) ||
    (/macintosh/i.test(userAgent) && (navigatorWithTouchPoints.maxTouchPoints ?? 0) > 1)
  );
}

function shouldShowInstallPrompt(): boolean {
  return (
    isMobileViewport() &&
    !isStandaloneDisplay() &&
    Date.now() > getDismissedUntil()
  );
}

/**
 * Shows a mobile-only install prompt when the browser can add AREQA to the home
 * screen.
 *
 * Side effects:
 * - Captures Chromium's `beforeinstallprompt` event so the install button can
 *   open the native browser prompt.
 * - Stores a short dismissal window in localStorage to avoid repeatedly
 *   interrupting returning mobile users.
 */
export const PwaInstallPrompt: React.FC = () => {
  const { styles } = useStyles();
  const [deferredPrompt, setDeferredPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [promptMode, setPromptMode] = useState<PromptMode | null>(null);

  useEffect(() => {
    if (!shouldShowInstallPrompt()) return;

    if (isIOSDevice()) {
      window.requestAnimationFrame(() => {
        setPromptMode('ios');
      });
    }

    const handleBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setDeferredPrompt(event as BeforeInstallPromptEvent);
      setPromptMode(shouldShowInstallPrompt() ? 'native' : null);
    };

    const handleAppInstalled = () => {
      setDeferredPrompt(null);
      setPromptMode(null);
      window.localStorage.removeItem(DISMISS_UNTIL_KEY);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const dismissPrompt = useCallback(() => {
    window.localStorage.setItem(
      DISMISS_UNTIL_KEY,
      String(Date.now() + DISMISS_DURATION_MS),
    );
    setPromptMode(null);
  }, []);

  const installPrompt = useCallback(async () => {
    if (!deferredPrompt) {
      dismissPrompt();
      return;
    }

    await deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    setDeferredPrompt(null);
    setPromptMode(null);
  }, [deferredPrompt, dismissPrompt]);

  const promptCopy = useMemo(() => {
    if (promptMode === 'ios') {
      return {
        icon: <Share2 size={20} aria-hidden="true" />,
        title: '加入 AREQA 到主畫面',
        description: '點選瀏覽器分享按鈕，選擇「加入主畫面」即可像 App 一樣開啟。',
        action: '知道了',
      };
    }

    return {
      icon: <Download size={20} aria-hidden="true" />,
      title: '安裝 AREQA',
      description: '把 AREQA 加到手機主畫面，之後可以用全螢幕 App 模式快速開啟。',
      action: '安裝',
    };
  }, [promptMode]);

  if (!promptMode) return null;

  return (
    <section className={styles.container} role="dialog" aria-live="polite">
      <Button
        aria-label="關閉安裝提示"
        className={styles.closeButton}
        icon={<X size={16} aria-hidden="true" />}
        onClick={dismissPrompt}
        shape="circle"
        type="text"
      />
      <div className={styles.header}>
        <div className={styles.iconWrap}>{promptCopy.icon}</div>
        <div>
          <Title className={styles.title} level={2}>
            {promptCopy.title}
          </Title>
          <Text className={styles.description}>{promptCopy.description}</Text>
        </div>
      </div>
      <div className={styles.actions}>
        <Button className={styles.installButton} onClick={installPrompt} type="primary">
          {promptCopy.action}
        </Button>
        <Button className={styles.laterButton} onClick={dismissPrompt}>
          稍後
        </Button>
      </div>
    </section>
  );
};
