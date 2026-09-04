/**
 * Live Tutor inline voice-mode styles.
 *
 * ChatContainer renders this panel between the conversation and the normal
 * composer. The component owns only the voice affordance, leaving text input
 * layout and keyboard-safe behavior to ChatInput.
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({
  panel: css`
    position: relative;
    display: flex;
    width: 100%;
    --live-tutor-audio-level: 0;
    --live-tutor-audio-scale: 1;
    min-height: 0;
    flex: 1 1 auto;
    flex-direction: column;
    overflow: hidden;
    padding: 8px clamp(16px, 4vw, 44px) 12px;
    background: var(--background);
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

  header: css`
    display: flex;
    min-height: 42px;
    align-items: center;
    justify-content: space-between;
    gap: 12px;

    @media (max-width: 768px) {
      min-height: 38px;
    }
  `,

  body: css`
    display: grid;
    min-height: 0;
    flex: 1 1 auto;
    grid-template-rows: auto minmax(0, 1fr);
    align-items: center;
    padding-bottom: 4px;

    @media (max-width: 768px) {
      padding-bottom: 0;
    }
  `,

  status: css`
    color: color-mix(in srgb, var(--foreground) 64%, transparent);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0;

    @media (max-width: 768px) {
      font-size: 12px;
    }
  `,

  voiceCore: css`
    display: grid;
    min-height: 0;
    grid-row: 2;
    place-items: center;
    align-self: center;
    justify-self: center;
  `,

  logoOrb: css`
    position: relative;
    width: clamp(76px, 8vw, 108px);
    aspect-ratio: 1;
    border-radius: 50%;
    box-shadow:
      0 10px 28px rgba(17, 24, 39, 0.14),
      0 0 calc(12px + var(--live-tutor-audio-level) * 32px) rgba(127, 140, 255, 0.3);
    transform: scale(var(--live-tutor-audio-scale)) translateZ(0);
    transform-origin: center;
    transition: transform 90ms linear, box-shadow 120ms linear;
    will-change: transform;

    &::after {
      position: absolute;
      content: '';
      border-radius: inherit;
      pointer-events: none;
      inset: -14%;
      background: radial-gradient(circle, rgba(127, 140, 255, calc(0.12 + var(--live-tutor-audio-level) * 0.18)), transparent 66%);
      filter: blur(10px);
      z-index: -1;
    }

    @media (max-width: 768px) {
      width: clamp(88px, 24vw, 116px);
      box-shadow:
        0 12px 34px rgba(17, 24, 39, 0.12),
        0 0 calc(14px + var(--live-tutor-audio-level) * 36px) rgba(127, 140, 255, 0.3);
    }
  `,

  logoImage: css`
    display: block;
    width: 100%;
    height: auto;
    border-radius: 50%;
    user-select: none;
  `,

  logoOrbActive: css`
    animation: liveTutorLogoRestingPulse 2.4s ease-in-out infinite;

    @keyframes liveTutorLogoRestingPulse {
      0%, 100% {
        filter: saturate(1);
      }
      50% {
        filter: saturate(1.08);
      }
    }

    @media (prefers-reduced-motion: reduce) {
      animation: none;
    }
  `,

  controlCluster: css`
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    gap: 8px;

    @media (max-width: 768px) {
      gap: 6px;
    }
  `,

  muteButton: css`
    display: inline-flex;
    width: 38px;
    height: 38px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: color-mix(in srgb, var(--foreground) 86%, transparent);
    cursor: pointer;
    transition: background 0.16s ease, color 0.16s ease, transform 0.16s ease;

    &:hover {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      color: var(--foreground);
      transform: translateY(-1px);
    }

    @media (max-width: 768px) {
      width: 36px;
      height: 36px;
    }
  `,

  closeButton: css`
    display: inline-flex;
    width: 42px;
    height: 42px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: color-mix(in srgb, var(--foreground) 92%, transparent);
    color: var(--background);
    cursor: pointer;
    transition: background 0.16s ease, transform 0.16s ease;

    &:hover {
      background: var(--foreground);
      transform: translateY(-1px);
    }

    @media (max-width: 768px) {
      width: 38px;
      height: 38px;
    }
  `,

  errorRow: css`
    display: flex;
    width: min(680px, 100%);
    align-items: center;
    grid-row: 1;
    justify-self: center;
    gap: 8px;
    padding: 4px 0;
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
