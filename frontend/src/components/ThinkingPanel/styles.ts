/**
 * ThinkingPanel Styles
 * CSS-in-JS styles using antd-style
 */

import { createStyles, keyframes } from 'antd-style';

const shine = keyframes`
  0% {
    background-position: 200% center;
  }
  100% {
    background-position: -200% center;
  }
`;

const pulse = keyframes`
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
`;

export const useStyles = createStyles(({ css, token }) => ({
  container: css`
    overflow: hidden;
    border-radius: ${token.borderRadiusLG}px;
    background: ${token.colorFillSecondary};
    border: 1px solid ${token.colorBorderSecondary};
    transition: all 0.2s ${token.motionEaseOut};
  `,

  header: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    cursor: pointer;
    user-select: none;

    &:hover {
      background: ${token.colorFillTertiary};
    }
  `,

  headerLeft: css`
    display: flex;
    align-items: center;
    gap: 8px;
  `,

  headerRight: css`
    display: flex;
    align-items: center;
    gap: 4px;
  `,

  icon: css`
    color: ${token.colorTextTertiary};
    transition: transform 0.2s ${token.motionEaseOut};
  `,

  iconExpanded: css`
    transform: rotate(90deg);
  `,

  thinkingLabel: css`
    font-size: 14px;
    color: rgba(255, 255, 255, 0.85);
  `,

  shinyText: css`
    background: linear-gradient(
      120deg,
      rgba(255, 255, 255, 0.45) 40%,
      rgba(255, 255, 255, 0.95) 50%,
      rgba(255, 255, 255, 0.45) 60%
    );
    background-clip: text;
    -webkit-background-clip: text;
    color: transparent;
    background-size: 200% 100%;
    animation: ${shine} 1.5s linear infinite;
  `,

  duration: css`
    font-size: 13px;
    color: rgba(255, 255, 255, 0.5);
  `,

  content: css`
    padding: 12px 16px;
    border-top: 1px solid ${token.colorBorderSecondary};
    font-size: 16px;
    line-height: 1.6;
    color: ${token.colorTextSecondary};
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 400px;
    overflow-y: auto;
  `,

  copyButton: css`
    opacity: 0.6;
    transition: opacity 0.2s;

    &:hover {
      opacity: 1;
    }
  `,

  thinkingIndicator: css`
    display: inline-flex;
    align-items: center;
    gap: 4px;
  `,

  dot: css`
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: ${token.colorTextTertiary};
    animation: ${pulse} 1s ease-in-out infinite;

    &:nth-child(2) {
      animation-delay: 0.2s;
    }

    &:nth-child(3) {
      animation-delay: 0.4s;
    }
  `,

  emptyContent: css`
    color: ${token.colorTextQuaternary};
    font-style: italic;
  `,
}));
