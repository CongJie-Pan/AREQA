/**
 * ChatContainer Styles
 * CSS-in-JS styles using antd-style
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css, token }) => ({
  container: css`
    position: fixed;
    top: 0;
    right: 0;
    bottom: auto;
    left: 0;
    display: flex;
    height: var(--areqa-visual-viewport-height, 100dvh);
    width: 100vw;
    min-height: 0;
    overflow: hidden;
    background: var(--background);
  `,

  sidebar: css`
    width: 280px;
    flex: 0 0 280px;
    transition: all 0.2s ${token.motionEaseOut};
    background: var(--areqa-sidebar-background);
    border-right: 1px solid var(--areqa-subtle-border);
    overflow: hidden;

    @media (max-width: 768px) {
      position: fixed;
      left: 0;
      top: 0;
      height: 100%;
      z-index: 100;
      transform: translateX(-100%);
    }
  `,

  sidebarOpen: css`
    @media (max-width: 768px) {
      transform: translateX(0);
    }

    @media (min-width: 769px) {
      width: 0;
      flex-basis: 0;
      border-right: none;
    }
  `,

  sidebarOverlay: css`
    display: none;

    @media (max-width: 768px) {
      display: block;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.7);
      z-index: 99;
    }
  `,

  main: css`
    position: relative;
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    overscroll-behavior: contain;
    background: var(--background);
  `,

  floatingActions: css`
    position: absolute;
    top: max(14px, env(safe-area-inset-top));
    right: max(16px, env(safe-area-inset-right));
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 8px;
    pointer-events: none;
  `,

  sidebarFloatingAction: css`
    position: fixed;
    top: max(14px, env(safe-area-inset-top));
    left: max(16px, env(safe-area-inset-left));
    z-index: 120;
    display: flex;
    align-items: center;
    pointer-events: none;
  `,

  iconActionButton: css`
    pointer-events: auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: ${token.borderRadius}px;
    background: color-mix(in srgb, var(--background) 86%, transparent);
    color: ${token.colorTextSecondary};
    cursor: pointer;
    touch-action: manipulation;
    transition: all 0.2s;
    backdrop-filter: blur(10px);

    &:hover {
      background: ${token.colorFillTertiary};
      color: ${token.colorText};
    }
  `,

  sidebarActionButton: css`
    display: none;

    @media (max-width: 768px) {
      display: flex;
    }
  `,

  sidebarActionButtonVisible: css`
    @media (max-width: 768px) {
      display: none;
    }

    @media (min-width: 769px) {
      display: flex;
    }
  `,

  shareButton: css`
    pointer-events: auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: ${token.borderRadius}px;
    background: color-mix(in srgb, var(--background) 86%, transparent);
    color: ${token.colorText};
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.2s;
    backdrop-filter: blur(10px);

    &:hover:not(:disabled) {
      background: ${token.colorFillTertiary};
    }

    &:disabled {
      cursor: progress;
      opacity: 0.62;
    }

    svg {
      color: #d8a25c;
      flex-shrink: 0;
    }
  `,

  content: css`
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
    overscroll-behavior: contain;
  `,

  /* When chat is empty, center the greeting + input together vertically */
  contentEmpty: css`
    justify-content: center;
    padding-bottom: 18vh;

    /* Remove flex-grow from messageArea so it wraps content naturally */
    & > div:first-child {
      flex: none;
    }

    /* Make input narrower and centered horizontally */
    & > div:last-child {
      max-width: 768px;
      width: 100%;
      align-self: center;
    }
  `,

  messageArea: css`
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
  `,

  inputArea: css`
    flex-shrink: 0;

    @media (max-width: 768px) {
      padding-bottom: max(env(safe-area-inset-bottom), 0px);
    }
  `,

  errorBanner: css`
    padding: 12px 16px;
    background: ${token.colorErrorBg};
    border-bottom: 1px solid ${token.colorErrorBorder};
    color: ${token.colorError};
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 8px;
  `,

  errorDismiss: css`
    margin-left: auto;
    cursor: pointer;
    opacity: 0.7;

    &:hover {
      opacity: 1;
    }
  `,
}));
