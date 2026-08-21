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

const verticalReveal = keyframes`
  from {
    opacity: 0;
    transform: translateY(8px);
    filter: blur(2px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
    filter: blur(0);
  }
`;

const messageShellReveal = keyframes`
  from {
    opacity: 0;
    transform: translateY(4px);
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

const imageSkeletonShimmer = keyframes`
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
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

  emptyLogo: css`
    width: 260px;
    height: auto;
    object-fit: contain;

    @media (max-width: 768px) {
      width: 180px;
    }
  `,

  emptySubtitle: css`
    font-family: "Times New Roman", Times, serif;
    margin-top: -18px;
    color: rgba(255, 255, 255, 0.6);
    text-align: center;
    font-size: 1.1rem;
    letter-spacing: 0.5px;

    span {
      font-weight: bold;
      font-size: 1.2em;
      color: rgba(255, 255, 255, 0.85);
    }

    @media (max-width: 768px) {
      font-size: 0.9rem;
      margin-top: -12px;
      padding: 0 16px;
    }
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

    @media (max-width: 768px) {
      width: 100%;
      padding: 12px 16px;
    }

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
    background: #1f1b2b;
    color: #ffffff;
    align-self: flex-end;
    padding: 12px 18px;
    border-radius: 18px;
    border-bottom-right-radius: 4px;
    max-width: 85%;
    width: auto;

    @media (max-width: 768px) {
      max-width: 95%;
      padding: 10px 14px;
      border-radius: 16px;
      border-bottom-right-radius: 4px;
    }
  `,

  messageAttachmentList: css`
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    align-self: flex-end;
    align-items: flex-end;
    gap: 8px;
    margin-top: 8px;
    max-width: 85%;

    @media (max-width: 768px) {
      max-width: 95%;
    }
  `,

  messageAttachmentCard: css`
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 180px;
    max-width: 320px;
    padding: 8px 12px;
    border: 1px solid rgba(255, 255, 255, 0.13);
    border-radius: 12px;
    background: rgba(0, 0, 0, 0.16);
    color: rgba(255, 255, 255, 0.9);
  `,

  messageAttachmentIcon: css`
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 30px;
    width: 30px;
    height: 30px;
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.08);
    color: #d8a25c;
  `,

  messageAttachmentDetails: css`
    display: flex;
    min-width: 0;
    flex-direction: column;
    line-height: 1.3;
  `,

  messageAttachmentName: css`
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
  `,

  messageAttachmentMeta: css`
    margin-top: 2px;
    color: rgba(255, 255, 255, 0.48);
    font-size: 11px;
  `,

  messageAttachmentToggleWrap: css`
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    max-width: min(560px, 100%);
  `,

  messageAttachmentToggle: css`
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-height: 48px;
    padding: 7px 14px 7px 8px;
    border: 1px solid rgba(255, 255, 255, 0.11);
    border-radius: 14px;
    background: #1b1b1d;
    color: rgba(255, 255, 255, 0.72);
    cursor: pointer;
    font-size: 17px;
    line-height: 1;
    transition: border-color 0.2s ease, background 0.2s ease;

    &:hover {
      border-color: rgba(255, 255, 255, 0.2);
      background: #222225;
    }
  `,

  messageAttachmentToggleIcon: css`
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.8);
  `,

  messageAttachmentToggleChevron: css`
    color: rgba(255, 255, 255, 0.48);
    transition: transform 0.2s ease;
  `,

  messageAttachmentToggleChevronOpen: css`
    transform: rotate(180deg);
  `,

  messageAttachmentPopoverContainer: css`
    max-width: none !important;
    padding: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
  `,

  messageAttachmentDropdown: css`
    width: min(632px, calc(100vw - 32px));
    max-height: min(560px, calc(100vh - 96px));
    overflow-y: auto;
    padding: 14px 18px;
    border: 1px solid rgba(255, 255, 255, 0.13);
    border-radius: 16px;
    background: #19191a;
    color: rgba(255, 255, 255, 0.88);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
  `,

  messageAttachmentDropdownItem: css`
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 0;
    padding: 9px 0;

    & + & {
      border-top: 1px solid rgba(255, 255, 255, 0.06);
    }
  `,

  messageAttachmentDropdownIcon: css`
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    color: rgba(255, 255, 255, 0.78);
  `,

  messageAttachmentDropdownName: css`
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 18px;
  `,

  assistantBubble: css`
    background: transparent;
    color: #f0f0f0;
    align-self: flex-start;
  `,

  assistantBubbleReveal: css`
    animation: ${messageShellReveal} 200ms ease-out both;

    @media (prefers-reduced-motion: reduce) {
      animation: none;
    }
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

  blockquote {
    margin: 12px 0;
    padding: 2px 0 2px 16px;
    border-left: 3px solid rgba(255, 255, 255, 0.25);
    color: rgba(255, 255, 255, 0.6);
    
    p {
      margin-bottom: 0;
    }
  }

  code {
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

  table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 14px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 8px;
    overflow: hidden;
  }

  th, td {
    border: 1px solid rgba(255, 255, 255, 0.15);
    padding: 10px 12px;
    text-align: left;
  }

  th {
    background: rgba(255, 255, 255, 0.08);
    font-weight: 600;
  }

  tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.03);
  }
`,

streamingContentReveal: css`
  position: relative;

  @media (prefers-reduced-motion: reduce) {
    transform: none;
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

  citationsReveal: css`
    animation: ${verticalReveal} 240ms cubic-bezier(0.16, 1, 0.3, 1) 120ms both;

    @media (prefers-reduced-motion: reduce) {
      animation: none;
    }
  `,

  answerImageCard: css`
    width: min(100%, 520px);
    margin: 18px auto;
    overflow: hidden;
    border-radius: 18px;
    background: transparent;
    animation: ${verticalReveal} 260ms cubic-bezier(0.16, 1, 0.3, 1) both;

    @media (prefers-reduced-motion: reduce) {
      animation: none;
    }
  `,

  answerImageExplanation: css`
    margin: 12px 0 10px;
    color: rgba(255, 255, 255, 0.86);
    font-size: 15px;
    line-height: 1.8;
    animation: ${verticalReveal} 220ms cubic-bezier(0.16, 1, 0.3, 1) both;

    @media (prefers-reduced-motion: reduce) {
      animation: none;
    }
  `,

  answerImageButton: css`
    position: relative;
    display: block;
    width: 100%;
    padding: 0;
    border: 0;
    border-radius: 18px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.06);
    cursor: zoom-in;

    &:focus-visible {
      outline: 2px solid ${token.colorPrimary};
      outline-offset: 3px;
    }
  `,

  answerImagePendingFrame: css`
    position: relative;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.05);
  `,

  answerImagePendingLabel: css`
    position: absolute;
    left: 50%;
    bottom: 16px;
    z-index: 1;
    max-width: calc(100% - 32px);
    transform: translateX(-50%);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: rgba(255, 255, 255, 0.78);
    font-size: 13px;
    line-height: 1.45;
    text-align: center;
  `,

  answerImageSkeletonLayer: css`
    position: absolute;
    inset: 0;
    z-index: 1;
    pointer-events: none;
    opacity: 1;
    transition: opacity 220ms ease;
  `,

  answerImageSkeleton: css`
    width: 100%;
    height: 100%;
    min-height: 180px;
    border-radius: 18px;
    background: linear-gradient(
      90deg,
      rgba(255, 255, 255, 0.06),
      rgba(255, 255, 255, 0.12),
      rgba(255, 255, 255, 0.06)
    );
    background-size: 400% 100%;
    animation: ${imageSkeletonShimmer} 1.2s ease-in-out infinite;
  `,

  answerImage: css`
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #ffffff;
    opacity: 0;
    transform: scale(0.992);
    transition: opacity 260ms ease, transform 260ms ease;
  `,

  answerImageLoaded: css`
    opacity: 1;
    transform: scale(1);
  `,

  answerImageCaption: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 2px 0;
    color: rgba(255, 255, 255, 0.72);
    font-size: 12px;
    line-height: 1.5;
    opacity: 0;
    transform: translateY(-2px);
    transition: opacity 220ms ease 80ms, transform 220ms ease 80ms;
  `,

  answerImageCaptionVisible: css`
    opacity: 1;
    transform: translateY(0);
  `,

  answerImageCaptionText: css`
    color: rgba(255, 255, 255, 0.78);
    font-size: 13px;
    font-style: italic;
  `,

  answerImageMetaLine: css`
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    color: rgba(255, 255, 255, 0.58);
    font-size: 12px;
  `,

  answerImageLicense: css`
    display: inline-flex;
    align-items: center;
    min-height: 18px;
    padding: 1px 5px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.74);
  `,

  answerImageSource: css`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    width: fit-content;
    color: ${token.colorLink};
    font-size: 12px;
    text-decoration: none;

    &:hover {
      color: ${token.colorLinkHover};
      text-decoration: underline;
    }
  `,

  answerImageLightbox: css`
    .ant-modal-content {
      background: #111111;
      border: 1px solid rgba(255, 255, 255, 0.12);
    }

    .ant-modal-header {
      background: transparent;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .ant-modal-title,
    .ant-modal-close {
      color: rgba(255, 255, 255, 0.88);
    }
  `,

  answerImageLightboxBody: css`
    display: grid;
    gap: 16px;
  `,

  answerImageLightboxImage: css`
    display: block;
    width: 100%;
    max-height: 70vh;
    object-fit: contain;
    border-radius: 8px;
    background: #ffffff;
  `,

  answerImageLightboxMeta: css`
    display: grid;
    gap: 8px;
    color: rgba(255, 255, 255, 0.74);
    font-size: 13px;
    line-height: 1.6;

    p {
      margin: 0;
    }

    a {
      color: ${token.colorLink};
    }
  `,

  answerImageLightboxSource: css`
    display: inline-flex;
    align-items: center;
    gap: 6px;
    width: fit-content;
    color: ${token.colorLink};
    text-decoration: none;

    &:hover {
      color: ${token.colorLinkHover};
      text-decoration: underline;
    }
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
    background: #6f2f45;
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
      background: #853752;
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

  actionButtonActive: css`
    color: #d8a25c;
    background: rgba(216, 162, 92, 0.14);

    &:hover {
      color: #f0c987;
      background: rgba(216, 162, 92, 0.2);
    }
  `,

  feedbackActionSlot: css`
    display: inline-flex;
    width: 32px;
    overflow: hidden;
    opacity: 1;
    transform: translateX(0);
    transition: width 0.2s ease, opacity 0.2s ease, transform 0.2s ease;
  `,

  feedbackActionSlotCollapsed: css`
    width: 0;
    opacity: 0;
    pointer-events: none;
    transform: translateX(-8px);
  `,

  feedbackModal: css`
    .ant-modal-content {
      padding: 22px 20px 20px;
      border-radius: 16px;
      background: #202020;
      color: #f2f2f2;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.46);
    }

    .ant-modal-close {
      color: rgba(255, 255, 255, 0.86);
    }

    .ant-modal-close:hover {
      color: #ffffff;
      background: rgba(255, 255, 255, 0.08);
    }
  `,

  feedbackSheetWrap: css`
    @media (max-width: 768px) {
      position: fixed !important;
      top: var(--areqa-visual-viewport-top, 0) !important;
      right: 0 !important;
      bottom: auto !important;
      left: 0 !important;
      display: flex;
      align-items: flex-end;
      height: var(--areqa-visual-viewport-height, 100dvh) !important;
      overflow: hidden !important;
      overscroll-behavior: contain;

      .ant-modal {
        top: auto !important;
        width: 100vw !important;
        max-width: 100vw;
        margin: 0 !important;
        padding: 0 !important;
      }
    }
  `,

  feedbackSheetModal: css`
    top: auto;
    margin: 0;
    max-width: 100vw;
    padding-bottom: 0;

    .ant-modal-content {
      max-height: min(calc(var(--areqa-visual-viewport-height, 100dvh) - 24px), 640px);
      overflow-y: auto;
      border: 1px solid rgba(216, 162, 92, 0.16);
      border-radius: 24px 24px 0 0;
      background: #1e1826;
      color: #f5f0ea;
      padding: 16px 20px calc(18px + env(safe-area-inset-bottom));
      box-shadow: 0 -18px 48px rgba(0, 0, 0, 0.42);
    }

    @media (max-width: 768px) {
      width: 100vw !important;
      position: relative;
      right: 0;
      bottom: 0;
      left: 0;
    }
  `,

  feedbackForm: css`
    display: flex;
    flex-direction: column;
    gap: 16px;

    @media (max-width: 768px) {
      gap: 14px;
    }
  `,

  feedbackSheetHandle: css`
    width: 48px;
    height: 5px;
    margin: 0 auto 8px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.36);
  `,

  feedbackTitle: css`
    color: inherit;
    font-size: 18px;
    font-weight: 500;

    @media (max-width: 768px) {
      text-align: center;
      font-size: 22px;
      font-weight: 600;
      line-height: 1.25;
    }
  `,

  desktopFeedbackReasons: css`
    display: flex;
    flex-wrap: wrap;
    gap: 10px;

    @media (max-width: 768px) {
      display: none;
    }
  `,

  feedbackReasonChip: css`
    min-height: 42px;
    padding: 0 16px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 999px;
    background: transparent;
    color: rgba(255, 255, 255, 0.9);
    cursor: pointer;
    font-size: 15px;
    transition: border-color 0.2s ease, background 0.2s ease, color 0.2s ease;

    &:hover {
      border-color: rgba(216, 162, 92, 0.7);
      color: #ffffff;
    }
  `,

  feedbackReasonChipSelected: css`
    border-color: #d8a25c;
    background: rgba(216, 162, 92, 0.16);
    color: #f0c987;
  `,

  mobileFeedbackReason: css`
    display: none;

    @media (max-width: 768px) {
      display: block;
    }
  `,

  feedbackLabel: css`
    margin-bottom: 8px;
    color: rgba(245, 240, 234, 0.74);
    font-size: 14px;
    line-height: 1.2;
  `,

  feedbackSelect: css`
    width: 100%;

    .ant-select-selector {
      min-height: 48px;
      border: 1px solid rgba(216, 162, 92, 0.28) !important;
      border-radius: 12px !important;
      background: rgba(255, 255, 255, 0.06) !important;
      color: #f5f0ea !important;
      box-shadow: none !important;
    }

    .ant-select-selection-placeholder,
    .ant-select-selection-item {
      display: flex;
      align-items: center;
      min-height: 46px;
      color: rgba(245, 240, 234, 0.72) !important;
      font-size: 16px;
    }

    .ant-select-arrow {
      color: rgba(245, 240, 234, 0.68);
    }
  `,

  mobileFeedbackNativeSelect: css`
    width: 100%;
    min-height: 50px;
    padding: 0 44px 0 14px;
    border: 1px solid rgba(216, 162, 92, 0.28);
    border-radius: 12px;
    background:
      linear-gradient(45deg, transparent 50%, rgba(245, 240, 234, 0.68) 50%) right 18px center / 8px 8px no-repeat,
      linear-gradient(135deg, rgba(245, 240, 234, 0.68) 50%, transparent 50%) right 12px center / 8px 8px no-repeat,
      rgba(255, 255, 255, 0.06);
    color: #f5f0ea;
    font: inherit;
    font-size: 16px;
    line-height: 1.2;
    outline: none;
    appearance: none;
    -webkit-appearance: none;

    &:focus {
      border-color: rgba(216, 162, 92, 0.82);
      box-shadow: 0 0 0 2px rgba(216, 162, 92, 0.18);
    }

    option {
      background: #241d2e;
      color: #f5f0ea;
    }
  `,

  feedbackSelectDropdown: css`
    max-height: min(44dvh, 320px);
    overflow-y: auto;
    background: #241d2e;
    border: 1px solid rgba(216, 162, 92, 0.22);
    border-radius: 14px;
    padding: 6px;

    .ant-select-item {
      min-height: 42px;
      padding: 10px 12px;
      border-radius: 10px;
      color: #f5f0ea;
      font-size: 15px;
      font-weight: 500;
    }

    .ant-select-item-option-active,
    .ant-select-item-option-selected {
      background: rgba(216, 162, 92, 0.16) !important;
    }
  `,

  feedbackTextArea: css`
    &.ant-input {
      resize: vertical;
      border-color: rgba(255, 255, 255, 0.15);
      border-radius: 12px;
      background: #202020;
      color: #f2f2f2;
      font-size: 15px;
      box-shadow: none;
    }

    &.ant-input::placeholder {
      color: rgba(255, 255, 255, 0.46);
    }

    &.ant-input:hover,
    &.ant-input:focus {
      border-color: rgba(216, 162, 92, 0.65);
      box-shadow: none;
    }

    @media (max-width: 768px) {
      &.ant-input {
        min-height: 150px;
        border: 1px solid rgba(216, 162, 92, 0.24);
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.06);
        color: #f5f0ea;
        font-size: 16px;
        line-height: 1.55;
      }

      &.ant-input::placeholder {
        color: rgba(245, 240, 234, 0.5);
      }
    }
  `,

  feedbackPrivacyText: css`
    padding: 10px 14px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.12);
    color: rgba(255, 255, 255, 0.76);
    font-size: 14px;
    line-height: 1.45;

    @media (max-width: 768px) {
      padding: 0;
      background: transparent;
      color: rgba(245, 240, 234, 0.54);
      font-size: 13px;
    }
  `,

  feedbackSubmitRow: css`
    display: flex;
    justify-content: flex-end;

    @media (max-width: 768px) {
      margin-top: 2px;
    }
  `,

  feedbackSubmitButton: css`
    min-width: 64px;
    height: 44px;
    border: 0;
    border-radius: 999px;
    background: #5f5f5f;
    color: #ffffff;

    &.ant-btn-primary:not(:disabled):hover {
      background: #707070;
      color: #ffffff;
    }

    &.ant-btn:disabled {
      background: #3f3f3f;
      color: rgba(255, 255, 255, 0.34);
    }

    @media (max-width: 768px) {
      width: 100%;
      height: 52px;
      font-size: 16px;
      font-weight: 700;
      background: #d8a25c;
      color: #130f18;

      &.ant-btn:disabled {
        background: rgba(255, 255, 255, 0.12);
        color: rgba(245, 240, 234, 0.34);
      }
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
      border-color: #d8a25c;
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
    background: #d8a25c;
    color: #ffffff;

    &:hover {
      background: #e2b478;
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
