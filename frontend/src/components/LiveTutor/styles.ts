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
    --live-tutor-audio-scale: 1;
    min-height: 0;
    flex: 1 1 auto;
    flex-direction: column;
    overflow: visible;
    pointer-events: none;
    padding: 8px clamp(16px, 4vw, 44px) 12px;
    background: transparent;
    color: var(--foreground);

    @media (max-width: 768px) {
      padding: 8px 18px 10px;
    }
  `,

  panelWithMessages: css`
    flex: 0 0 0;
    height: 0;
    padding: 0;
    z-index: 2;

    & > div {
      position: absolute;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 160px;
    }
  `,

  panelWithFloatingAvatar: css`
    flex: 0 0 0;
    height: 0;
    padding: 0;
    z-index: 3;

    & > div {
      position: static;
      width: 0;
      height: 0;
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

  avatarStage: css`
    display: grid;
    position: relative;
    width: auto;
    place-items: center;
    overflow: visible;
    background: transparent;
  `,

  avatarStageActive: css`
    width: clamp(156px, 18vw, 220px);
    aspect-ratio: 4 / 5;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--foreground) 14%, transparent);
    border-radius: 8px;
    background: #101010;
    box-shadow: 0 14px 42px rgba(0, 0, 0, 0.32);

    @media (max-width: 768px) {
      width: clamp(148px, 42vw, 190px);
    }
  `,

  avatarStageSpeaking: css`
    box-shadow:
      0 14px 42px rgba(0, 0, 0, 0.34),
      0 0 0 1px color-mix(in srgb, #facd8a 34%, transparent);
  `,

  avatarVideo: css`
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0;
    transition: opacity 180ms ease;
  `,

  avatarVideoReady: css`
    opacity: 1;
  `,

  floatingAvatarWindow: css`
    pointer-events: auto;
    position: fixed;
    top: 0;
    left: 0;
    z-index: 40;
    width: clamp(184px, 17vw, 240px);
    aspect-ratio: 4 / 5;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--foreground) 16%, transparent);
    border-radius: 8px;
    background: #101010;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.36);
    touch-action: none;
    user-select: none;

    @media (max-width: 768px) {
      width: clamp(136px, 42vw, 176px);
      box-shadow: 0 12px 34px rgba(0, 0, 0, 0.34);
    }
  `,

  floatingAvatarSpeaking: css`
    box-shadow:
      0 16px 48px rgba(0, 0, 0, 0.38),
      0 0 0 1px color-mix(in srgb, #facd8a 36%, transparent);

    @media (max-width: 768px) {
      box-shadow:
        0 12px 34px rgba(0, 0, 0, 0.36),
        0 0 0 1px color-mix(in srgb, #facd8a 36%, transparent);
    }
  `,

  floatingAvatarHandle: css`
    position: absolute;
    top: 6px;
    left: 50%;
    z-index: 2;
    display: inline-flex;
    width: 38px;
    height: 24px;
    align-items: center;
    justify-content: center;
    transform: translateX(-50%);
    border: 0;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.48);
    color: rgba(255, 255, 255, 0.82);
    cursor: grab;
    opacity: 0.78;
    touch-action: none;
    transition: opacity 140ms ease, background 140ms ease;

    &:hover,
    &:focus-visible {
      background: rgba(0, 0, 0, 0.62);
      opacity: 1;
      outline: none;
    }

    &:active {
      cursor: grabbing;
    }
  `,

  floatingAvatarVideo: css`
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
    background: #101010;
  `,

  statusText: css`
    pointer-events: none;
    color: color-mix(in srgb, var(--foreground) 74%, transparent);
    font-size: 14px;
    font-weight: 500;
    line-height: 1.4;
  `,

  avatarNotice: css`
    pointer-events: none;
    position: absolute;
    bottom: calc(50% + 70px);
    left: 50%;
    width: min(520px, calc(100vw - 40px));
    padding: 7px 10px;
    transform: translateX(-50%);
    border: 1px solid color-mix(in srgb, #facd8a 32%, transparent);
    border-radius: 6px;
    background: color-mix(in srgb, #1d1b18 88%, transparent);
    color: color-mix(in srgb, #fff6df 90%, transparent);
    font-size: 13px;
    font-weight: 500;
    line-height: 1.4;
    text-align: center;
  `,

  logoOrb: css`
    width: clamp(78px, 8vw, 104px);
    aspect-ratio: 1;
    transform: scale(var(--live-tutor-audio-scale)) translateZ(0);
    transform-origin: center;
    transition: transform 70ms linear;
    filter: drop-shadow(0 0 14px color-mix(in srgb, #e3ba80 68%, transparent))
      drop-shadow(0 0 38px color-mix(in srgb, #e3ba80 30%, transparent));
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
    background: transparent;
  `,

  errorRow: css`
    pointer-events: auto;
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
