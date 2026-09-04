/**
 * Live Tutor inline voice-mode styles.
 *
 * ChatContainer renders this panel between the conversation and the normal
 * composer. The component owns only the floating logo and error feedback;
 * ChatInput owns all voice controls while the session is active.
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({
  panel: css`
    position: relative;
    display: flex;
    width: 100%;
    --live-tutor-audio-scale: 0.9;
    min-height: 0;
    flex: 1 1 auto;
    flex-direction: column;
    overflow: hidden;
    padding: 8px clamp(16px, 4vw, 44px) 12px;
    background: transparent;
    color: var(--foreground);

    @media (max-width: 768px) {
      padding: 8px 18px 10px;
    }
  `,

  panelWithMessages: css`
    flex: 0 0 clamp(150px, 25dvh, 230px);

    @media (max-width: 768px) {
      flex-basis: clamp(150px, 24dvh, 210px);
    }
  `,

  body: css`
    display: grid;
    position: relative;
    min-height: 0;
    flex: 1 1 auto;
    place-items: center;
    padding-bottom: 4px;

    @media (max-width: 768px) {
      padding-bottom: 0;
    }
  `,

  voiceCore: css`
    display: grid;
    min-height: 0;
    place-items: center;
  `,

  logoOrb: css`
    width: clamp(78px, 8vw, 104px);
    aspect-ratio: 1;
    transform: scale(var(--live-tutor-audio-scale)) translateZ(0);
    transform-origin: center;
    transition: transform 70ms linear;
    will-change: transform;

    @media (max-width: 768px) {
      width: clamp(84px, 24vw, 108px);
    }
  `,

  logoImage: css`
    display: block;
    width: 100%;
    height: auto;
    border-radius: 50%;
    user-select: none;
  `,

  errorRow: css`
    position: absolute;
    top: 0;
    left: 50%;
    display: flex;
    width: min(680px, 100%);
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    transform: translateX(-50%);
    z-index: 1;
  `,

  error: css`
    min-width: 0;
    flex: 1;
    padding: 8px 12px;
    border: 1px solid rgba(255, 92, 92, 0.46);
    border-radius: 6px;
    background: rgba(180, 52, 52, 0.18);
    color: #ffd7d7;
    font-size: 13px;
    line-height: 1.45;
    text-align: center;

    @media (max-width: 768px) {
      font-size: 13px;
    }
  `,

  retryButton: css`
    display: inline-flex;
    width: 34px;
    height: 34px;
    flex: 0 0 34px;
    align-items: center;
    justify-content: center;
    border: 1px solid color-mix(in srgb, var(--foreground) 18%, transparent);
    border-radius: 50%;
    background: transparent;
    color: var(--foreground);
    cursor: pointer;

    &:hover {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
    }
  `,
}));
