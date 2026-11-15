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
  // Composer geometry lives in globals.css so it is available before hydration.
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

  inputRowRecording: css`
    gap: 10px;
  `,

  attachmentList: css`
    display: flex;
    flex-wrap: nowrap;
    gap: 10px;
    width: 100%;
    margin: 0 0 12px;
    overflow-x: auto;
    padding: 2px 2px 8px;
    scrollbar-width: thin;
    scrollbar-color: color-mix(in srgb, var(--foreground) 30%, transparent) transparent;

    @media (max-width: 768px) {
      margin: 0 0 16px;
    }
  `,

  dropOverlay: css`
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(25, 25, 25, 0.72);
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
    color: color-mix(in srgb, var(--foreground) 90%, transparent);
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
    color: var(--foreground);
  `,

  addMenu: css`
    .ant-dropdown-menu {
      min-width: min(380px, calc(100vw - 32px));
      padding: 6px;
    }

    .ant-dropdown-menu-item {
      padding: 8px 10px;
    }
  `,

  addMenuItem: css`
    display: flex;
    min-width: 0;
    align-items: baseline;
    gap: 10px;
  `,

  addMenuItemTitle: css`
    flex: none;
    color: var(--foreground);
    font-weight: 500;
  `,

  addMenuItemDescription: css`
    overflow: hidden;
    min-width: 0;
    color: color-mix(in srgb, var(--foreground) 55%, transparent);
    text-overflow: ellipsis;
    white-space: nowrap;
  `,

  modeToken: css`
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 5px;
    max-width: 45%;
    color: #6ea8fe;
    font-size: 14px;
    line-height: 22px;

    svg {
      flex: none;
    }

    /* Collapsed but still focusable remove control; expands on hover/focus. */
    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 0;
      height: 18px;
      overflow: hidden;
      opacity: 0;
      padding: 0;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: color-mix(in srgb, var(--foreground) 55%, transparent);
      cursor: pointer;

      &:hover {
        background: color-mix(in srgb, var(--foreground) 12%, transparent);
        color: var(--foreground);
      }

      @media (hover: none) {
        width: 18px;
        opacity: 1;
      }
    }

    &:hover button,
    &:focus-within button {
      width: 18px;
      opacity: 1;
    }
  `,

  modeTokenLabel: css`
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    /* Narrow phones keep the textarea usable: icon only, name in the tooltip. */
    @media (max-width: 520px) {
      display: none;
    }
  `,

  recordingInactiveControl: css`
    color: color-mix(in srgb, var(--foreground) 28%, transparent);

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
    color: color-mix(in srgb, var(--foreground) 92%, transparent);

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      color: var(--foreground);
    }
  `,

  webSearchButton: css`
    background: transparent;
    color: color-mix(in srgb, var(--foreground) 72%, transparent);

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      color: var(--foreground);
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
    background: color-mix(in srgb, var(--foreground) 10%, transparent);
    color: color-mix(in srgb, var(--foreground) 94%, transparent);

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--foreground) 16%, transparent);
      color: var(--foreground);
    }
  `,

  avatarButtonInactive: css`
    color: color-mix(in srgb, var(--foreground) 58%, transparent);
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
    color: var(--foreground);

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
    }
  `,

  confirmDictationButton: css`
    background: transparent;
    color: var(--foreground);

    &:hover:not(:disabled) {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
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
      background: color-mix(in srgb, var(--foreground) calc(28% + var(--wave-level) * 58%), transparent);
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
      background: color-mix(in srgb, var(--foreground) calc(48% + var(--wave-level) * 48%), transparent);
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
    border: 1px solid color-mix(in srgb, var(--foreground) 20%, transparent);
    border-radius: 16px;
    background: transparent;
    color: color-mix(in srgb, var(--foreground) 65%, transparent);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
    &:hover {
      color: var(--foreground) !important;
      background: var(--muted) !important;
      border-color: color-mix(in srgb, var(--foreground) 40%, transparent) !important;
    }
`,

toggleButtonActive: css`
color: var(--foreground);
border-color: #d8a25c;
background: rgba(216, 162, 92, 0.15);
font-weight: 500;

&:hover {
  background: rgba(216, 162, 92, 0.25) !important;
  color: var(--foreground) !important;
  border-color: #e2b478 !important;
}
`,

  // Stubs kept for backward-compat so any old references don't cause TS errors
  inputWrapper: css`flex: 1;`,
  hint: css`display: none;`,
  actionBar: css`display: none;`,
}));
