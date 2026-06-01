/**
 * MessageList Styles
 * CSS-in-JS styles using antd-style
 */

import { createStyles, keyframes } from 'antd-style';

const fadeIn = keyframes`
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

const cursorBlink = keyframes`
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
    opacity: 0;
  }
`;

export const useStyles = createStyles(({ css, token }) => ({
  // MessageList styles
  container: css`
    display: flex;
    flex-direction: column;
    gap: 0;
    padding: 0;
    overflow-y: scroll; /* Force scrollbar to be always visible */
    flex: 1;
  `,

  empty: css`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    text-align: center;
    padding: 40px;
    gap: 14px;
  `,

  emptyTitle: css`
    font-size: 26px;
    font-weight: 700;
    color: ${token.colorText};
    margin: 0;
    line-height: 1.4;
    letter-spacing: -0.3px;
  `,

  emptyDescription: css`
    font-size: 15px;
    color: ${token.colorTextTertiary};
    margin: 0;
  `,

  // MessageItem styles
  messageItem: css`
    display: flex;
    flex-direction: column;
    padding: 12px 0;
    max-width: 800px;
    width: 90%;
    margin: 0 auto;
    animation: ${fadeIn} 0.3s ease-out;

    /* If an assistant message follows a user message, reduce the top padding even more */
    &.assistant-after-user {
      padding-top: 4px;
    }
  `,

  userMessage: css`
    align-items: flex-end;

    .bubbleWrapper {
      align-items: flex-end;
    }

    .userActionButtons {
      justify-content: flex-end;
    }
  `,

  // AI Message wrapper - vertical layout
  assistantMessageWrapper: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
  `,

  // AI Message header - model name, timestamp in a row
  assistantHeader: css`
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;

    &:hover .hoverTimestamp {
      opacity: 1;
    }
  `,

  modelName: css`
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
    white-space: nowrap;
  `,

  hoverTimestamp: css`
    font-size: 12px;
    color: rgba(255, 255, 255, 0.35);
    opacity: 0;
    transition: opacity 0.2s;
    margin-left: 4px;
  `,

  bubbleWrapper: css`
    display: flex;
    flex-direction: column;
    width: 100%;
    gap: 4px;
  `,

  bubble: css`
    padding: 12px 0;
    line-height: 1.8;
    word-break: break-word;
    overflow-wrap: anywhere;
    width: fit-content;
    max-width: 100%;
  `,

  userBubble: css`
    background: #2a2a2a;
    color: #ffffff;
    align-self: flex-end;
    padding: 12px 18px;
    border-radius: 18px;
    border-bottom-right-radius: 4px;
    max-width: 85%;
    width: auto;
  `,

  assistantBubble: css`
    background: transparent;
    color: #f0f0f0;
    align-self: flex-start;
  `,
content: css`
  font-size: 16px;
  line-height: 1.8;
  color: #e0e0e0;
  overflow-wrap: anywhere;
  word-break: break-word;

  p {
    margin: 0 0 8px 0;

    &:last-child {
      margin-bottom: 0;
    }
  }
`,

quoteBlock: css`
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 4px 0 10px 0;
  padding: 0;
  background: transparent;
  border-radius: 0;
  color: #999999;
  font-size: 13px;
  border: none;
  width: fit-content;
  max-width: 100%;
  transition: all 0.2s ease;
  font-style: italic;

  &.interactive-quote:hover {
    opacity: 0.8;
    transform: translateX(2px);
  }
`,

quoteBlockArrow: css`
  color: inherit;
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  display: inline-block;
  margin-top: 3px;
`,

quoteBlockContent: css`
  flex: 1;
  opacity: 0.9;
  line-height: 1.5;
  color: inherit;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  text-overflow: ellipsis;

  p {
    margin: 0;
    display: inline;
  }
`,

code: css`...
      padding: 2px 6px;
      background: ${token.colorFillTertiary};
      border-radius: ${token.borderRadiusSM}px;
      font-family: 'Monaco', 'Menlo', monospace;
      font-size: 13px;
    }

    pre {
      padding: 12px;
      background: ${token.colorFillQuaternary};
      border-radius: ${token.borderRadius}px;
      overflow-x: auto;

      code {
        padding: 0;
        background: transparent;
      }
    }

    ul, ol {
      margin: 8px 0;
      padding-left: 20px;
    }

    ul {
      list-style-type: disc;
    }

    ol {
      list-style-type: decimal;
    }

    li {
      margin: 4px 0;
    }

    a {
      color: ${token.colorLink};
      text-decoration: none;

      &:hover {
        text-decoration: underline;
      }
    }
  `,

  streamingCursor: css`
    display: inline-block;
    width: 2px;
    height: 16px;
    background: ${token.colorText};
    margin-left: 2px;
    vertical-align: text-bottom;
    animation: ${cursorBlink} 1s step-end infinite;
  `,

  thinkingPanelWrapper: css`
    margin-bottom: 12px;
  `,

  citationsWrapper: css`
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    width: 100%;
    min-width: 0;
  `,

  // Scroll to bottom button
  scrollButton: css`
    position: sticky;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: #8B1E1E;
    color: #ffffff;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
    transition: all 0.2s ease;
    z-index: 10;

    &:hover {
      background: #A82222;
      transform: translateX(-50%) scale(1.1);
    }

    &:active {
      transform: translateX(-50%) scale(0.95);
    }
  `,

  // Action buttons container
  actionButtons: css`
    display: flex;
    flex-direction: row;
    gap: 8px;
    margin-top: 4px;
  `,

  // Action button style (copy, regenerate)
  actionButton: css`
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: rgba(255, 255, 255, 0.4);
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      color: #ffffff;
      background: rgba(255, 255, 255, 0.1);
      transform: scale(1.1);
    }

    &:active {
      transform: scale(0.95);
    }
  `,

  // Legacy: keep for user messages
  copyButton: css`
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: rgba(255, 255, 255, 0.4);
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      color: #ffffff;
      background: rgba(255, 255, 255, 0.1);
    }
  `,

  // User message action buttons container
  userActionButtons: css`
    display: flex;
    gap: 8px;
    margin-top: 4px;
  `,

  // Edit mode container
  editModeContainer: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
  `,

  // Edit textarea
  editTextarea: css`
    width: 100%;
    min-height: 80px;
    padding: 12px 16px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.6;
    resize: vertical;
    outline: none;
    transition: border-color 0.2s;
    font-family: inherit;
    background: #1e1e1e;
    color: #ffffff;

    &:focus {
      border-color: #8B1E1E;
    }

    &::placeholder {
      color: rgba(255, 255, 255, 0.3);
    }
  `,

  // Edit mode buttons container
  editButtons: css`
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  `,

  // Edit mode button base
  editButton: css`
    padding: 6px 16px;
    border-radius: 8px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    border: none;
  `,

  // Save button
  editSaveButton: css`
    background: #8B1E1E;
    color: #ffffff;

    &:hover {
      background: #A82222;
    }

    &:disabled {
      background: #333333;
      color: rgba(255, 255, 255, 0.2);
      cursor: not-allowed;
    }
  `,

  // Cancel button
  editCancelButton: css`
    background: transparent;
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.1);

    &:hover {
      background: rgba(255, 255, 255, 0.05);
    }
  `,
}));
