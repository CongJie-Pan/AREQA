/**
 * ChatContainer Styles
 * CSS-in-JS styles using antd-style
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css, token }) => ({
  container: css`
    display: flex;
    height: 100vh;
    overflow: hidden;
    background: #1a1a1a;
  `,

  sidebar: css`
    width: 280px;
    flex-shrink: 0;
    transition: all 0.2s ${token.motionEaseOut};
    background: #2d2d2d;
    border-right: 1px solid rgba(255, 255, 255, 0.05);
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
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    background: #1a1a1a;
  `,

  header: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    background: #1a1a1a;
  `,

  headerLeft: css`
    display: flex;
    align-items: center;
    gap: 12px;
  `,

  menuButton: css`
    display: none;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: none;
    border-radius: ${token.borderRadius}px;
    background: transparent;
    color: ${token.colorTextSecondary};
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: ${token.colorFillTertiary};
    }

    @media (max-width: 768px) {
      display: flex;
    }
  `,

  menuButtonVisible: css`
    @media (min-width: 769px) {
      display: flex;
    }
  `,

  headerTitle: css`
    font-size: 16px;
    font-weight: 500;
    color: ${token.colorText};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  `,

  content: css`
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `,

  /* When chat is empty, center the greeting + input together vertically */
  contentEmpty: css`
    justify-content: center;
    padding-bottom: 15vh; /* Move the centered group upwards slightly */

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
  `,

  inputArea: css`
    flex-shrink: 0;
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
