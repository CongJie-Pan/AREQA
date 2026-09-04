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
    padding: 12px 20px 10px;
    background: var(--card);
    border-width: 1px;
    border-style: solid;
    border-color: var(--border);
    border-radius: 24px;
    max-width: 800px;
    width: 90%;
    margin: 0 auto 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    transition: all 0.2s ease;
    
    @media (max-width: 768px) {
      width: calc(100% - 24px);
      margin: 0 auto 12px;
      border-radius: 20px;
      border-width: 1px;
      border-style: solid;
      border-color: var(--border);
      padding: 10px 14px 8px;
    }

    &:focus-within {
      border-color: #d8a25c;
      box-shadow: 0 0 0 2px rgba(216, 162, 92, 0.2);
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
    min-height: 36px;
    gap: 12px;
  `,

  // Borderless textarea that fills the input row
  textarea: css`
    flex: 1 1 auto;
    width: 0;
    min-width: 0;
    min-height: 24px;
    max-height: 200px;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--foreground);
    font-size: 16px;
    line-height: 24px;
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
    color: var(--foreground);
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

  voiceButton: css`
    width: 36px;
    height: 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 36px;
    border: 1px solid rgba(216, 162, 92, 0.38);
    border-radius: 50%;
    background: rgba(216, 162, 92, 0.12);
    color: #d8a25c;
    cursor: pointer;
    transition: all 0.2s;

    &:hover:not(:disabled) {
      border-color: #d8a25c;
      background: rgba(216, 162, 92, 0.2);
      transform: translateY(-1px);
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.45;
    }
  `,

  // Circular send button aligned in the toolbar
  sendButton: css`
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid transparent;
    border-radius: 50%;
    background: ${token.colorPrimary};
    color: ${token.colorWhite};
    cursor: pointer;
    transition: all 0.2s;

    &:hover:not(:disabled) {
      background: ${token.colorPrimaryHover};
      transform: scale(1.05);
    }

    &:active:not(:disabled) {
      background: ${token.colorPrimaryActive};
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
    background: var(--foreground);
    color: var(--background);

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--foreground) 86%, transparent);
    }

    &:active:not(:disabled) {
      background: color-mix(in srgb, var(--foreground) 78%, transparent);
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
