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
    padding: clamp(10px, 1.6vw, 18px) clamp(16px, 4vw, 44px);
    background:
      radial-gradient(circle at 50% 62%, color-mix(in srgb, #7f8cff 12%, transparent), transparent 16rem),
      var(--background);
    color: var(--foreground);

    @media (max-width: 640px) {
      padding: 10px 26px 16px;
      background: var(--background);
    }
  `,

  header: css`
    display: flex;
    min-height: 42px;
    align-items: center;
    justify-content: space-between;
    gap: 12px;

    @media (max-width: 640px) {
      min-height: 38px;
    }
  `,

  body: css`
    display: grid;
    min-height: 0;
    flex: 1 1 auto;
    grid-template-rows: minmax(0, auto) auto minmax(0, 1fr);
    align-items: center;
    padding-bottom: clamp(6px, 2vh, 22px);

    @media (max-width: 640px) {
      grid-template-rows: minmax(0, 1fr) auto minmax(0, 2.2fr);
      padding-bottom: 0;
    }
  `,

  captionArea: css`
    display: flex;
    width: min(980px, 100%);
    min-width: 0;
    flex-direction: column;
    gap: 8px;
    justify-self: center;
    align-self: start;
    overflow-y: auto;
    padding-top: 4px;
    scrollbar-width: thin;
    scrollbar-color: color-mix(in srgb, var(--foreground) 28%, transparent) transparent;

    @media (max-width: 640px) {
      max-height: 86px;
      gap: 8px;
      align-self: end;
      padding-top: 0;
      text-align: center;
    }
  `,

  status: css`
    color: color-mix(in srgb, var(--foreground) 64%, transparent);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0;

    @media (max-width: 640px) {
      font-size: 12px;
    }
  `,

  transcriptText: css`
    color: var(--foreground);
    font-size: clamp(15px, 1.6vw, 20px);
    font-weight: 500;
    line-height: 1.55;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  `,

  secondaryTranscript: css`
    max-width: 760px;
    color: color-mix(in srgb, var(--foreground) 58%, transparent);
    font-size: clamp(13px, 1.25vw, 15px);
    line-height: 1.55;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  `,

  voiceCore: css`
    display: grid;
    min-height: clamp(150px, 26vh, 300px);
    place-items: center;
    align-self: center;
    justify-self: center;

    @media (max-width: 640px) {
      min-height: clamp(240px, 42dvh, 460px);
      align-self: center;
    }
  `,

  logoOrb: css`
    position: relative;
    width: clamp(132px, 15vw, 220px);
    aspect-ratio: 1;
    border-radius: 50%;
    box-shadow:
      0 16px 42px rgba(17, 24, 39, 0.16),
      0 0 calc(20px + var(--live-tutor-audio-level) * 46px) rgba(127, 140, 255, 0.34);
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

    @media (max-width: 640px) {
      width: clamp(214px, 54vw, 300px);
      box-shadow:
        0 18px 54px rgba(17, 24, 39, 0.12),
        0 0 calc(24px + var(--live-tutor-audio-level) * 56px) rgba(127, 140, 255, 0.32);
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

    @media (max-width: 640px) {
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

    @media (max-width: 640px) {
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

    @media (max-width: 640px) {
      width: 38px;
      height: 38px;
    }
  `,

  error: css`
    width: min(680px, 100%);
    justify-self: center;
    margin: 10px 0;
    padding: 9px 14px;
    border: 1px solid rgba(255, 92, 92, 0.46);
    border-radius: 999px;
    background: rgba(180, 52, 52, 0.18);
    color: #ffd7d7;
    font-size: 13px;
    line-height: 1.45;
    text-align: center;

    @media (max-width: 640px) {
      width: 100%;
      margin: 8px 0 4px;
      border-radius: 18px;
      font-size: 13px;
    }
  `,
}));
