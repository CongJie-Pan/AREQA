/**
 * RAGStatusPanel Styles
 * CSS-in-JS styles using antd-style
 */

import { createStyles, keyframes } from 'antd-style';

const radarPulse = keyframes`
  0% {
    transform: scale(0.5);
    opacity: 1;
  }
  100% {
    transform: scale(2.5);
    opacity: 0;
  }
`;

export const useStyles = createStyles(({ token, css }) => ({
  container: css`
    margin-bottom: 12px;
    padding: 4px 0;
    background: transparent;
    display: flex;
    flex-direction: column;
    gap: 8px;
  `,

  header: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    height: 32px;
  `,

  statusInfo: css`
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    margin-left: 14px;
  `,

  radarWrapper: css`
    position: relative;
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
  `,

  radarCore: css`
    width: 6px;
    height: 6px;
    background-color: ${token.colorPrimary};
    border-radius: 50%;
    z-index: 2;
  `,

  radarRing: css`
    position: absolute;
    width: 100%;
    height: 100%;
    border: 2px solid ${token.colorPrimary};
    border-radius: 50%;
    animation: ${radarPulse} 1.5s ease-out infinite;
    z-index: 1;
  `,

  checkIcon: css`
    color: ${token.colorSuccess};
  `,

  spinnerWrapper: css`
    display: flex;
    align-items: center;
    justify-content: center;
  `,

  routingIcon: css`
    color: ${token.colorPrimary};
  `,

  statusText: css`
    font-size: 16px;
    color: ${token.colorText};
    font-weight: 600;
  `,

  sourceCount: css`
    font-size: 13px;
    color: ${token.colorTextTertiary};
    background: ${token.colorFillSecondary};
    padding: 2px 10px;
    border-radius: 12px;
  `
}));
