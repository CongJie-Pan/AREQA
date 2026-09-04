/**
 * Live Tutor responsive panel styles.
 *
 * Desktop uses a compact floating panel so the existing chat remains readable.
 * Mobile uses a bottom sheet with safe-area padding because microphone controls
 * must stay reachable on Android and iPhone browsers.
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({
  overlay: css`
    position: fixed;
    inset: 0;
    z-index: 1300;
    pointer-events: none;

    @media (max-width: 768px) {
      display: flex;
      align-items: flex-end;
      background: rgba(0, 0, 0, 0.32);
      pointer-events: auto;
    }
  `,

  panel: css`
    position: absolute;
    right: 24px;
    bottom: 96px;
    display: flex;
    width: min(400px, calc(100vw - 32px));
    max-height: min(640px, calc(100vh - 128px));
    flex-direction: column;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 18px;
    background: color-mix(in srgb, var(--card) 94%, black);
    color: var(--foreground);
    box-shadow: 0 24px 72px rgba(0, 0, 0, 0.42);
    pointer-events: auto;

    @media (max-width: 768px) {
      position: relative;
      right: auto;
      bottom: auto;
      width: 100%;
      max-height: 88vh;
      min-height: 45vh;
      border-right: 0;
      border-bottom: 0;
      border-left: 0;
      border-radius: 22px 22px 0 0;
      padding-bottom: env(safe-area-inset-bottom);
    }
  `,

  header: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 16px 10px;
    border-bottom: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  `,

  titleGroup: css`
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 2px;
  `,

  title: css`
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 15px;
    font-weight: 700;
  `,

  status: css`
    color: var(--muted-foreground);
    font-size: 12px;
  `,

  iconButton: css`
    display: inline-flex;
    width: 36px;
    height: 36px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 50%;
    background: var(--muted);
    color: var(--foreground);
    cursor: pointer;
    transition: transform 0.16s ease, border-color 0.16s ease, background 0.16s ease;

    &:hover {
      border-color: #d8a25c;
      transform: translateY(-1px);
    }
  `,

  body: css`
    display: flex;
    flex: 1 1 auto;
    min-height: 0;
    flex-direction: column;
    gap: 14px;
    padding: 16px;
  `,

  avatarStage: css`
    display: flex;
    min-height: 170px;
    align-items: center;
    justify-content: center;
    border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
    border-radius: 14px;
    background:
      radial-gradient(circle at 50% 35%, rgba(216, 162, 92, 0.2), transparent 42%),
      var(--muted);

    @media (max-width: 768px) {
      min-height: 150px;
    }
  `,

  avatar: css`
    position: relative;
    display: grid;
    width: 112px;
    height: 112px;
    place-items: center;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.08);
  `,

  avatarPulse: css`
    position: absolute;
    inset: -10px;
    border: 1px solid rgba(216, 162, 92, 0.48);
    border-radius: 50%;
    animation: liveTutorPulse 1.6s ease-in-out infinite;

    @keyframes liveTutorPulse {
      0%, 100% { opacity: 0.28; transform: scale(0.95); }
      50% { opacity: 0.9; transform: scale(1.08); }
    }
  `,

  logo: css`
    width: 78px;
    height: 78px;
    border-radius: 50%;
    object-fit: cover;
  `,

  wave: css`
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    min-height: 24px;

    span {
      display: block;
      width: 4px;
      height: 12px;
      border-radius: 999px;
      background: #d8a25c;
      animation: liveTutorWave 0.9s ease-in-out infinite;
    }

    span:nth-child(2) { animation-delay: 0.1s; }
    span:nth-child(3) { animation-delay: 0.2s; }
    span:nth-child(4) { animation-delay: 0.3s; }

    @keyframes liveTutorWave {
      0%, 100% { transform: scaleY(0.55); opacity: 0.55; }
      50% { transform: scaleY(1.7); opacity: 1; }
    }
  `,

  transcript: css`
    display: flex;
    min-height: 150px;
    flex: 1 1 auto;
    flex-direction: column;
    gap: 10px;
    overflow-y: auto;
    border-radius: 12px;
  `,

  transcriptBlock: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 10px 12px;
    border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
    border-radius: 12px;
    background: color-mix(in srgb, var(--muted) 72%, transparent);
  `,

  transcriptLabel: css`
    color: var(--muted-foreground);
    font-size: 11px;
    font-weight: 700;
  `,

  transcriptText: css`
    color: var(--foreground);
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  `,

  controls: css`
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 0 16px 16px;
  `,

  primaryControl: css`
    display: inline-flex;
    width: 54px;
    height: 54px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: #d8a25c;
    color: #17120d;
    cursor: pointer;
  `,

  endControl: css`
    display: inline-flex;
    width: 54px;
    height: 54px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: #b43434;
    color: #ffffff;
    cursor: pointer;
  `,

  error: css`
    margin: 0 16px 12px;
    padding: 10px 12px;
    border: 1px solid rgba(180, 52, 52, 0.45);
    border-radius: 10px;
    background: rgba(180, 52, 52, 0.12);
    color: #ffd7d7;
    font-size: 13px;
  `,
}));
