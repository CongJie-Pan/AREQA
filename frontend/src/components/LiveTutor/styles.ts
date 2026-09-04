/**
 * Live Tutor fullscreen voice-mode styles.
 *
 * The layout mirrors modern voice chat UIs: readable caption area, a centered
 * ambient voice orb, and a bottom command bar that respects mobile safe areas.
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({
  overlay: css`
    position: fixed;
    inset: 0;
    z-index: 1300;
    background: #000000;
    color: #ffffff;
    pointer-events: auto;
  `,

  panel: css`
    position: relative;
    display: grid;
    width: 100%;
    min-height: 100dvh;
    grid-template-rows: minmax(150px, 0.95fr) auto minmax(120px, 1fr) auto;
    overflow: hidden;
    padding: clamp(18px, 3.2vw, 42px);
    padding-bottom: calc(clamp(18px, 3.2vw, 42px) + env(safe-area-inset-bottom));
    background:
      radial-gradient(circle at 50% 58%, rgba(91, 101, 255, 0.12), transparent 24rem),
      #000000;

    @media (max-width: 640px) {
      grid-template-rows: minmax(140px, 0.9fr) auto minmax(96px, 0.8fr) auto;
      padding: 18px 14px;
      padding-bottom: calc(14px + env(safe-area-inset-bottom));
    }
  `,

  captionArea: css`
    display: flex;
    width: min(980px, 100%);
    min-width: 0;
    flex-direction: column;
    gap: 14px;
    justify-self: center;
    overflow-y: auto;
    padding-top: clamp(4px, 1.6vh, 28px);
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.28) transparent;

    @media (max-width: 640px) {
      gap: 10px;
      padding-top: 0;
    }
  `,

  status: css`
    color: rgba(255, 255, 255, 0.64);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0;

    @media (max-width: 640px) {
      font-size: 12px;
    }
  `,

  transcriptText: css`
    color: #ffffff;
    font-size: clamp(17px, 2vw, 24px);
    font-weight: 500;
    line-height: 1.65;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  `,

  secondaryTranscript: css`
    max-width: 760px;
    color: rgba(255, 255, 255, 0.58);
    font-size: clamp(14px, 1.45vw, 17px);
    line-height: 1.55;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  `,

  voiceCore: css`
    display: grid;
    min-height: clamp(130px, 24vh, 260px);
    place-items: center;
    align-self: center;
    justify-self: center;
  `,

  orb: css`
    position: relative;
    width: clamp(86px, 10vw, 116px);
    aspect-ratio: 1;
    border-radius: 50%;
    background:
      radial-gradient(circle at 34% 26%, rgba(255, 255, 255, 0.95), transparent 10%),
      radial-gradient(circle at 31% 33%, rgba(255, 255, 255, 0.72), transparent 25%),
      radial-gradient(circle at 68% 28%, rgba(95, 88, 255, 0.95), transparent 34%),
      radial-gradient(circle at 64% 72%, rgba(235, 244, 255, 0.95), transparent 42%),
      linear-gradient(145deg, #8b8dff 0%, #eef5ff 48%, #c8d7ff 100%);
    box-shadow:
      0 0 28px rgba(112, 113, 255, 0.42),
      0 0 72px rgba(255, 255, 255, 0.14),
      inset -12px -14px 28px rgba(77, 89, 210, 0.22),
      inset 10px 10px 28px rgba(255, 255, 255, 0.52);
    transform: translateZ(0);

    &::before,
    &::after {
      position: absolute;
      content: '';
      border-radius: inherit;
      pointer-events: none;
    }

    &::before {
      inset: 12%;
      background: linear-gradient(35deg, transparent 0 26%, rgba(255, 255, 255, 0.52) 44%, transparent 68% 100%);
      filter: blur(3px);
      opacity: 0.88;
      transform: rotate(12deg);
    }

    &::after {
      inset: -18%;
      background: radial-gradient(circle, rgba(107, 116, 255, 0.24), transparent 62%);
      filter: blur(8px);
      opacity: 0.9;
      z-index: -1;
    }
  `,

  orbActive: css`
    animation: liveTutorOrbBreath 1.9s ease-in-out infinite;

    @keyframes liveTutorOrbBreath {
      0%, 100% {
        transform: scale(0.96);
        box-shadow:
          0 0 26px rgba(112, 113, 255, 0.36),
          0 0 66px rgba(255, 255, 255, 0.12),
          inset -12px -14px 28px rgba(77, 89, 210, 0.22),
          inset 10px 10px 28px rgba(255, 255, 255, 0.52);
      }
      50% {
        transform: scale(1.04);
        box-shadow:
          0 0 34px rgba(112, 113, 255, 0.58),
          0 0 94px rgba(255, 255, 255, 0.18),
          inset -12px -14px 28px rgba(77, 89, 210, 0.24),
          inset 10px 10px 30px rgba(255, 255, 255, 0.58);
      }
    }
  `,

  bottomBar: css`
    display: flex;
    width: min(1058px, 100%);
    min-height: 70px;
    align-items: center;
    justify-self: center;
    gap: 12px;
    padding: 8px 10px 8px 18px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    background: rgba(35, 35, 35, 0.98);
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.45);

    @media (max-width: 640px) {
      min-height: 62px;
      gap: 9px;
      padding: 7px 8px 7px 13px;
    }
  `,

  addButton: css`
    display: inline-flex;
    width: 40px;
    height: 40px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: rgba(255, 255, 255, 0.92);
    cursor: pointer;
    transition: background 0.16s ease, color 0.16s ease;

    &:hover {
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
    }

    @media (max-width: 640px) {
      width: 36px;
      height: 36px;
    }
  `,

  inputDivider: css`
    width: 1px;
    height: 28px;
    flex: 0 0 auto;
    background: rgba(255, 255, 255, 0.34);
  `,

  inputPlaceholder: css`
    min-width: 0;
    flex: 1 1 auto;
    color: rgba(255, 255, 255, 0.62);
    font-size: 19px;
    line-height: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    @media (max-width: 640px) {
      font-size: 17px;
    }
  `,

  controlCluster: css`
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    gap: 10px;

    @media (max-width: 640px) {
      gap: 7px;
    }
  `,

  muteButton: css`
    display: inline-flex;
    width: 48px;
    height: 48px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: rgba(255, 255, 255, 0.9);
    cursor: pointer;
    transition: background 0.16s ease, color 0.16s ease, transform 0.16s ease;

    &:hover {
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
      transform: translateY(-1px);
    }

    @media (max-width: 640px) {
      width: 44px;
      height: 44px;
    }
  `,

  closeButton: css`
    display: inline-flex;
    width: 54px;
    height: 54px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: #f4f4f4;
    color: #121212;
    cursor: pointer;
    transition: background 0.16s ease, transform 0.16s ease;

    &:hover {
      background: #ffffff;
      transform: translateY(-1px);
    }

    @media (max-width: 640px) {
      width: 48px;
      height: 48px;
    }
  `,

  error: css`
    width: min(720px, 100%);
    justify-self: center;
    margin: 0 0 16px;
    padding: 10px 14px;
    border: 1px solid rgba(255, 92, 92, 0.46);
    border-radius: 999px;
    background: rgba(180, 52, 52, 0.18);
    color: #ffd7d7;
    font-size: 13px;
    line-height: 1.45;
    text-align: center;
  `,
}));
