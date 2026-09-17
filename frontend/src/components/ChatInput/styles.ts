/**
 * ChatInput Styles
 * CSS-in-JS styles using antd-style
 *
 * DeepSeek-style layout: the textarea and toolbar are stacked inside a single
 * rounded container. The toolbar holds mode-toggle pills on the left and the
 * circular send button on the right — all on the same horizontal line.
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css, token }) => ({
  // Outer container: column-flex card that highlights on focus-within
  container: css`
    display: flex;
    flex-direction: column;
    gap: 0;
    padding: 8px 12px;
    background: #242424;
    border-width: 1px;
    border-style: solid;
    border-color: rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    max-width: 800px;
    width: min(90%, 800px);
    margin: 0 auto 12px;
    box-shadow: 0 10px 22px rgba(0, 0, 0, 0.28);
    transition: all 0.2s ease;
    
    @media (max-width: 768px) {
      width: calc(100% - 24px);
      margin: 0 auto 12px;
      border-radius: 999px;
      border-width: 1px;
      border-style: solid;
      border-color: rgba(255, 255, 255, 0.08);
      padding: 7px 10px;
    }

    &:focus-within {
      border-color: rgba(255, 255, 255, 0.18);
      box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08), 0 10px 22px rgba(0, 0, 0, 0.28);
    }
  `,

  containerWithAttachments: css`
    border-radius: 34px;
    padding: 12px 16px 10px;

    @media (max-width: 768px) {
      border-radius: 28px;
      padding: 10px 12px 9px;
    }
  `,

  containerExpanded: css`
    border-radius: 34px;
    padding: 12px 16px 10px;

    @media (max-width: 768px) {
      border-radius: 28px;
      padding: 10px 12px 9px;
    }
  `,

  quotePreview: css`
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    margin-bottom: 10px;
    background: var(--muted);
    border-radius: 20px;
    color: var(--foreground);
    font-size: 15px;
    position: relative;
    max-width: 100%;
    animation: slideDown 0.2s ease-out;

    @keyframes slideDown {
      from { opacity: 0; transform: translateY(-8px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `,

  quoteArrow: css`
    color: #d8a25c;
    flex-shrink: 0;
    width: 16px;
    height: 16px;
  `,

  quoteContent: css`
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    opacity: 0.9;
    color: var(--foreground);
    font-weight: 500;
  `,

  quoteClose: css`
    flex-shrink: 0;
    margin-left: 4px;
    width: 18px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: var(--muted-foreground);
    cursor: pointer;
    border-radius: 50%;
    transition: all 0.2s;

    &:hover {
      background: var(--areqa-account-hover);
      color: var(--foreground);
    }
  `,

  inputRow: css`
    display: flex;
    align-items: center;
    width: 100%;
    min-width: 0;
    min-height: 34px;
    gap: 8px;
  `,

  inputRowRecording: css`
    gap: 10px;
  `,

  // Borderless textarea that fills the input row
  textarea: css`
    flex: 1 1 auto;
    width: 0;
    min-width: 0;
    min-height: 22px;
    max-height: 200px;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--foreground);
    font-size: 15px;
    line-height: 22px;
    resize: none;
    outline: none;

    &::placeholder {
      color: var(--muted-foreground);
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.5;
    }
  `,

  mathPreview: css`
    margin: 4px 0 8px;
    padding: 8px 12px;
    border: 1px solid rgba(216, 162, 92, 0.2);
    border-radius: 8px;
    background: var(--muted);
    color: var(--foreground);
    overflow-x: auto;

    .katex-display {
      margin: 0.4em 0;
    }

    p:last-child {
      margin-bottom: 0;
    }
  `,

  mathPreviewLabel: css`
    margin-bottom: 4px;
    color: rgba(216, 162, 92, 0.8);
    font-size: 11px;
  `,

  attachmentList: css`
    display: flex;
    flex-wrap: nowrap;
    gap: 10px;
    width: 100%;
    margin: 0 0 18px;
    overflow-x: auto;
    padding: 0 2px 2px;

    @media (max-width: 768px) {
      margin: 0 0 16px;
    }
  `,

  attachmentChip: css`
    display: inline-flex;
    align-items: center;
    gap: 10px;
    flex: 0 0 auto;
    width: min(320px, 76vw);
    min-height: 58px;
    padding: 9px 10px;
    border-width: 1px;
    border-style: solid;
    border-color: color-mix(in srgb, #d8a25c 22%, var(--border));
    border-radius: 12px;
    background: color-mix(in srgb, var(--muted) 82%, #d8a25c 5%);
    color: var(--foreground);
    font-size: 14px;
    box-shadow: 0 10px 22px rgba(0, 0, 0, 0.18);

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: var(--muted-foreground);
      cursor: pointer;
      width: 26px;
      height: 26px;
      flex: 0 0 26px;

      &:hover {
        background: color-mix(in srgb, var(--foreground) 8%, transparent);
        color: var(--foreground);
      }
    }
  `,

  attachmentIconFrame: css`
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    flex: 0 0 34px;
    border-radius: 9px;
    background: color-mix(in srgb, #d8a25c 16%, transparent);
    color: #d8a25c;
  `,

  imageAttachmentChip: css`
    position: relative;
    width: 68px;
    height: 68px;
    flex: 0 0 68px;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--foreground) 14%, transparent);
    border-radius: 18px;
    background: color-mix(in srgb, var(--muted) 82%, #ffffff 6%);
    box-shadow: 0 8px 18px rgba(0, 0, 0, 0.22);

    @media (max-width: 768px) {
      width: 58px;
      height: 58px;
      flex-basis: 58px;
      border-radius: 16px;
    }
  `,

  imageAttachmentRemove: css`
    position: absolute;
    top: 4px;
    right: 4px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border: 0;
    border-radius: 999px;
    background: rgba(16, 16, 18, 0.76);
    color: rgba(255, 255, 255, 0.92);
    cursor: pointer;
    backdrop-filter: blur(8px);

    &:hover {
      background: rgba(16, 16, 18, 0.92);
      color: #ffffff;
    }
  `,

  attachmentDetails: css`
    display: flex;
    flex: 1 1 auto;
    min-width: 0;
    flex-direction: column;
    gap: 3px;

    > span {
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      line-height: 1.25;
    }

    small {
      color: var(--muted-foreground);
      font-size: 11px;
      line-height: 1.2;
    }
  `,

  attachmentThumbnail: css`
    width: 100%;
    height: 100%;
    display: block;
    border-radius: inherit;
    object-fit: cover;
    background: rgba(255, 255, 255, 0.08);
  `,

  attachmentFileIcon: css`
    flex: 0 0 auto;
    color: #d8a25c;
  `,

  dropOverlay: css`
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(19, 15, 24, 0.72);
    backdrop-filter: blur(6px);
    pointer-events: none;
  `,

  dropOverlayPanel: css`
    display: flex;
    width: min(420px, 100%);
    min-height: 160px;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border: 1px dashed rgba(216, 162, 92, 0.75);
    border-radius: 18px;
    background: color-mix(in srgb, var(--card) 92%, transparent);
    color: var(--foreground);
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.36);
    text-align: center;
  `,

  dropOverlayTitle: css`
    color: var(--foreground);
    font-size: 18px;
    font-weight: 700;
  `,

  dropOverlaySubtitle: css`
    color: var(--muted-foreground);
    font-size: 13px;
  `,

  // Bottom row: left-side mode pills + right-side send button
  toolbar: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 4px;
    gap: 8px;
  `,

  toolbarLeft: css`
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
  `,

  toolbarRight: css`
    display: flex;
    align-items: center;
    flex-shrink: 0;
  `,

  attachmentButton: css`
    width: 30px;
    height: 30px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: rgba(255, 255, 255, 0.9);
    cursor: pointer;
    transition: all 0.2s;

    &:hover:not(:disabled) {
      background: var(--areqa-account-hover);
      color: var(--foreground);
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.45;
    }
  `,

  attachmentButtonActive: css`
    background: color-mix(in srgb, #d8a25c 18%, transparent);
    color: #f4c47a;
  `,

  addMenuTutorItem: css`
    display: flex;
    min-width: 190px;
    flex-direction: column;
    gap: 2px;

    small {
      color: rgba(255, 255, 255, 0.58);
      font-size: 11px;
      line-height: 14px;
    }
  `,

  tutorProfileBar: css`
    display: flex;
    width: 100%;
    margin: 0 0 8px;
  `,

  tutorProfileChip: css`
    display: inline-flex;
    align-items: center;
    gap: 7px;
    min-height: 28px;
    padding: 4px 7px 4px 9px;
    border: 1px solid color-mix(in srgb, #d8a25c 28%, transparent);
    border-radius: 999px;
    background: color-mix(in srgb, #d8a25c 16%, transparent);
    color: #f2d19d;
    font-size: 12px;
    line-height: 16px;

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      padding: 0;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: currentColor;
      cursor: pointer;

      &:hover {
        background: color-mix(in srgb, #ffffff 12%, transparent);
      }
    }
  `,

  recordingInactiveControl: css`
    color: rgba(255, 255, 255, 0.28);

    &:disabled {
      opacity: 1;
    }
  `,

  iconButton: css`
    width: 34px;
    height: 34px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 34px;
    border: 0;
    border-radius: 50%;
    cursor: pointer;
    transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease, opacity 0.18s ease;

    &:hover:not(:disabled) {
      transform: translateY(-1px);
    }

    &:active:not(:disabled) {
      transform: translateY(0) scale(0.98);
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.42;
    }
  `,

  dictationButton: css`
    background: transparent;
    color: rgba(255, 255, 255, 0.92);

    &:hover:not(:disabled) {
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
    }
  `,

  webSearchButton: css`
    background: transparent;
    color: rgba(255, 255, 255, 0.72);

    &:hover:not(:disabled) {
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
    }
  `,

  webSearchButtonActive: css`
    background: #d7f7df;
    color: #0f5f2a;

    &:hover:not(:disabled) {
      background: #c2f0cf;
      color: #0a4c20;
    }
  `,

  voiceButton: css`
    background: #facd8a;
    color: #111111;

    &:hover:not(:disabled) {
      background: #ffd9a3;
    }

    &:active:not(:disabled) {
      background: #edbb72;
    }
  `,

  avatarButton: css`
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.94);

    &:hover:not(:disabled) {
      background: rgba(255, 255, 255, 0.16);
      color: #ffffff;
    }
  `,

  avatarButtonInactive: css`
    color: rgba(255, 255, 255, 0.58);
  `,

  // Circular send button aligned in the toolbar
  sendButton: css`
    background: #facd8a;
    color: #111111;

    &:hover:not(:disabled) {
      background: #ffd9a3;
    }

    &:active:not(:disabled) {
      background: #edbb72;
    }

    &:disabled {
      background: var(--muted);
      border-color: var(--border);
      color: var(--muted-foreground);
      cursor: not-allowed;
    }
  `,

  stopButton: css`
    background: ${token.colorError};

    &:hover:not(:disabled) {
      background: ${token.colorErrorHover};
    }

    &:active:not(:disabled) {
      background: ${token.colorErrorActive};
    }
  `,

  liveVoiceCloseButton: css`
    background: #f1f1f1;
    color: #111111;

    &:hover:not(:disabled) {
      background: #ffffff;
    }

    &:active:not(:disabled) {
      background: #e0e0e0;
    }
  `,

  cancelDictationButton: css`
    background: transparent;
    color: #ffffff;

    &:hover:not(:disabled) {
      background: rgba(255, 255, 255, 0.08);
    }
  `,

  confirmDictationButton: css`
    background: transparent;
    color: #ffffff;

    &:hover:not(:disabled) {
      background: rgba(255, 255, 255, 0.08);
    }
  `,

  dictationWave: css`
    --wave-level: 0.16;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: clamp(2px, 0.42vw, 5px);
    flex: 1 1 auto;
    min-width: 0;
    max-width: min(62vw, 460px);
    height: 30px;
    margin: 0 auto;
    overflow: hidden;
    mask-image: linear-gradient(
      90deg,
      transparent 0,
      #000 9%,
      #000 91%,
      transparent 100%
    );

    span {
      width: clamp(2px, 0.36vw, 4px);
      height: 24px;
      flex: 0 0 clamp(2px, 0.36vw, 4px);
      border-radius: 999px;
      background: rgba(255, 255, 255, calc(0.28 + var(--wave-level) * 0.58));
      transform-origin: center;
      transform: scaleY(calc(0.16 + var(--wave-level) * 0.84));
      transition:
        transform 150ms cubic-bezier(0.22, 1, 0.36, 1),
        background 150ms ease,
        opacity 150ms ease;
    }

    span:nth-child(4n + 1) {
      opacity: 0.72;
    }

    span:nth-child(5n + 2) {
      transform: scaleY(calc(0.12 + var(--wave-level) * 0.72));
    }

    span:nth-child(n + 13):nth-child(-n + 22) {
      background: rgba(255, 255, 255, calc(0.48 + var(--wave-level) * 0.48));
    }

    @media (max-width: 560px) {
      max-width: min(56vw, 260px);
      gap: 2px;
    }
  `,

  // Pill-shaped mode toggle buttons with icon + label text
  toggleButton: css`
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 12px;
    height: 32px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 16px;
    background: transparent;
    color: rgba(255, 255, 255, 0.65);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
    &:hover {
      color: #ffffff !important;
      background: #3a3a3a !important;
      border-color: rgba(255, 255, 255, 0.4) !important;
    }
`,

toggleButtonActive: css`
color: #ffffff;
border-color: #d8a25c;
background: rgba(216, 162, 92, 0.15);
font-weight: 500;

&:hover {
  background: rgba(216, 162, 92, 0.25) !important;
  color: #ffffff !important;
  border-color: #e2b478 !important;
}
`,

  // Stubs kept for backward-compat so any old references don't cause TS errors
  inputWrapper: css`flex: 1;`,
  hint: css`display: none;`,
  actionBar: css`display: none;`,
}));
