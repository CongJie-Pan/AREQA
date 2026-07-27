'use client';

import { useEffect, useState } from 'react';
import { createStyles } from 'antd-style';

const LAUNCH_SCREEN_VISIBLE_MS = 1800;
const LAUNCH_SCREEN_FADE_MS = 280;

const useStyles = createStyles(({ css }) => ({
  overlay: css`
    position: fixed;
    inset: 0;
    z-index: 2147483647;
    display: flex;
    align-items: stretch;
    justify-content: center;
    overflow: hidden;
    background: #130f18;
    opacity: 1;
    transition: opacity ${LAUNCH_SCREEN_FADE_MS}ms ease;
    pointer-events: none;
  `,
  hidden: css`
    opacity: 0;
  `,
  image: css`
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
    user-select: none;
    -webkit-user-drag: none;
  `,
}));

function isStandalonePwa(): boolean {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return false;
  }

  const navigatorWithStandalone = navigator as Navigator & {
    standalone?: boolean;
  };

  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    navigatorWithStandalone.standalone === true
  );
}

/**
 * Shows a branded launch screen only when AREQA is opened as an installed PWA.
 *
 * The browser-controlled Android splash screen cannot use a separate full-screen
 * image from the manifest, so this component provides the first app-rendered
 * frame without changing the home-screen app icon.
 */
export function PwaLaunchScreen() {
  const { styles, cx } = useStyles();
  const [shouldRender, setShouldRender] = useState(() => isStandalonePwa());
  const [isFadingOut, setIsFadingOut] = useState(false);

  useEffect(() => {
    if (!shouldRender) {
      return;
    }

    const fadeTimer = window.setTimeout(() => {
      setIsFadingOut(true);
    }, LAUNCH_SCREEN_VISIBLE_MS);

    const removeTimer = window.setTimeout(() => {
      setShouldRender(false);
    }, LAUNCH_SCREEN_VISIBLE_MS + LAUNCH_SCREEN_FADE_MS);

    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(removeTimer);
    };
  }, [shouldRender]);

  if (!shouldRender) {
    return null;
  }

  return (
    <div className={cx(styles.overlay, isFadingOut && styles.hidden)} aria-hidden="true">
      <img
        className={styles.image}
        src="/icon/start_screen.png"
        alt=""
        decoding="async"
        draggable={false}
      />
    </div>
  );
}
