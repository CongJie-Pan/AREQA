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
    gap: 6px;
    width: 100%;
    margin: 0 0 12px;
    overflow-x: auto;
    padding-bottom: 2px;

    @media (max-width: 768px) {
      margin: 0 0 10px;
    }
  `,

  attachmentChip: css`
    display: inline-flex;
    align-items: center;
    gap: 5px;
    flex: 0 0 auto;
    max-width: min(360px, 72vw);
    min-height: 44px;
    padding: 7px 10px;
    border-width: 1px;
    border-style: solid;
    border-color: var(--border);
    border-radius: 10px;
    background: var(--muted);
    color: var(--foreground);
    font-size: 13px;

    > span {
      display: flex;
      flex-direction: column;
      min-width: 0;
      gap: 1px;
    }

    > span > span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 180px;
    }

    small {
      color: var(--muted-foreground);
      font-size: 11px;
      line-height: 1.2;
    }

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      border: 0;
      background: transparent;
      color: inherit;
      cursor: pointer;
    }
  `,

  attachmentThumbnail: css`
    width: 36px;
    height: 36px;
    flex: 0 0 auto;
    border-radius: 8px;
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

  // Circular send button aligned in the toolbar
  sendButton: css`
    background: #2f6bdc;
    color: #ffffff;

    &:hover:not(:disabled) {
      background: #3d7bef;
    }

    &:active:not(:disabled) {
      background: #255cc5;
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
    justify-content: flex-end;
    gap: 3px;
    flex: 1 1 auto;
    min-width: 0;
    height: 24px;
    overflow: hidden;

    span {
      width: 3px;
      height: calc(4px + var(--wave-level) * 20px);
      flex: 0 0 3px;
      border-radius: 999px;
      background: rgba(255, 255, 255, calc(0.36 + var(--wave-level) * 0.52));
      transform-origin: center;
      transition: height 72ms linear, background 72ms linear;
    }

    span:nth-last-child(-n + 16) {
      background: rgba(255, 255, 255, 0.8);
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
