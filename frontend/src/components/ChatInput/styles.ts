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
    background: #2a2a2a;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 24px;
    max-width: 800px;
    width: 90%;
    margin: 0 auto 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    transition: all 0.2s ease;

    &:focus-within {
      border-color: #ff4d4f;
      box-shadow: 0 0 0 2px rgba(255, 77, 79, 0.2);
    }
  `,

  quotePreview: css`
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    margin-bottom: 10px;
    background: #333333;
    border-radius: 20px;
    color: #f0f0f0;
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
    color: #ff4d4f;
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
    color: #ffffff;
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
    color: rgba(255, 255, 255, 0.4);
    cursor: pointer;
    border-radius: 50%;
    transition: all 0.2s;

    &:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #ffffff;
    }
  `,

  // Borderless textarea that fills the top of the card
  textarea: css`
    width: 100%;
    min-height: 44px;
    max-height: 200px;
    padding: 8px 0;
    border: none;
    background: transparent;
    color: #ffffff;
    font-size: 16px;
    line-height: 1.5;
    resize: none;
    outline: none;

    &::placeholder {
      color: rgba(255, 255, 255, 0.5);
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.5;
    }
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

  // Faint character counter
  charCount: css`
    font-size: 11px;
    color: rgba(255, 255, 255, 0.45);
    margin-left: 4px;
  `,

  // Circular send button aligned in the toolbar
  sendButton: css`
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
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
      background: ${token.colorBgContainerDisabled};
      color: ${token.colorTextDisabled};
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
border-color: #ff4d4f;
background: rgba(255, 77, 79, 0.2);
font-weight: 500;

&:hover {
  background: rgba(255, 77, 79, 0.3) !important;
  color: #ffffff !important;
  border-color: #ff7875 !important;
}
`,

  // Stubs kept for backward-compat so any old references don't cause TS errors
  inputWrapper: css`flex: 1;`,
  hint: css`display: none;`,
  actionBar: css`display: none;`,
}));
