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

const sourceFocusPulse = keyframes`
  0% {
    box-shadow: 0 0 0 0 rgba(217, 119, 6, 0);
    background: rgba(217, 119, 6, 0);
  }
  18% {
    box-shadow: 0 0 0 2px rgba(217, 119, 6, 0.52);
    background: rgba(217, 119, 6, 0.1);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(217, 119, 6, 0);
    background: rgba(217, 119, 6, 0);
  }
`;

const streamingDotCycleStart = keyframes`
  0%, 6%, 18%, 30%, 42%, 54%, 66%, 72%, 100% {
    opacity: 0.35;
    transform: translate(0, 0) scale(1);
  }
  10%, 34%, 58% {
    opacity: 1;
    transform: translate(0, -2px) scale(1);
  }
  78%, 84% {
    opacity: 0.92;
    transform: translate(4px, 7px) scale(0.95);
  }
  90%, 93% {
    opacity: 1;
    transform: translate(12px, 0) scale(0.68);
  }
  97% {
    opacity: 0.9;
    transform: translate(-3px, 0) scale(1.12);
  }
`;

const streamingDotCycleMiddle = keyframes`
  0%, 10%, 22%, 34%, 46%, 58%, 70%, 72%, 100% {
    opacity: 0.35;
    transform: translateY(0) scale(1);
  }
  14%, 38%, 62% {
    opacity: 1;
    transform: translateY(-2px) scale(1);
  }
  78%, 84% {
    opacity: 1;
    transform: translateY(-8px) scale(1.16);
  }
  90%, 93% {
    opacity: 1;
    transform: translateY(0) scale(0.72);
  }
  97% {
    opacity: 0.9;
    transform: translateY(0) scale(1.12);
  }
`;

const streamingDotCycleEnd = keyframes`
  0%, 14%, 26%, 38%, 50%, 62%, 72%, 100% {
    opacity: 0.35;
    transform: translate(0, 0) scale(1);
  }
  18%, 42%, 66% {
    opacity: 1;
    transform: translate(0, -2px) scale(1);
  }
  78%, 84% {
    opacity: 0.92;
    transform: translate(-4px, 7px) scale(0.95);
  }
  90%, 93% {
    opacity: 1;
    transform: translate(-12px, 0) scale(0.68);
  }
  97% {
    opacity: 0.9;
    transform: translate(3px, 0) scale(1.12);
  }
`;

const emptyLogoFloat = keyframes`
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-20px);
  }
`;

const emptyLogoShadowPulse = keyframes`
  0%, 100% {
    opacity: 0.88;
    transform: translateX(-50%) scale(1.08);
  }
  50% {
    opacity: 0.44;
    transform: translateX(-50%) scale(0.58);
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

const tableModalBackdropIn = keyframes`
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
`;

const tableModalPanelIn = keyframes`
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
`;

export const useStyles = createStyles(({ css, token }) => ({
  viewport: css`
    position: relative;
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  `,

  voiceSpacer: css`
    height: 168px;
    min-height: 168px;
    flex: 0 0 168px;
    pointer-events: none;
  `,

  scrollButtonSpacer: css`
    height: 88px;
    min-height: 88px;
    flex: 0 0 88px;
    pointer-events: none;
  `,
  // MessageList styles
  container: css`
    display: flex;
    flex-direction: column;
    gap: 0;
    padding: 0;
    overflow-y: auto;
    flex: 1;
  `,

  containerLiveVoice: css`
    scroll-padding-bottom: 168px;
  `,

  nonEmpty: css`
    @media (max-width: 768px) {
      padding-top: calc(64px + env(safe-area-inset-top));
    }
  `,

  empty: css`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 0 1 auto;
    width: 100%;
    align-self: stretch;
    box-sizing: border-box;
    min-height: 0;
    text-align: center;
    padding: clamp(16px, 4vh, 30px) 24px clamp(10px, 2vh, 18px);
    gap: clamp(8px, 2vh, 14px);
  `,

  emptyLogoStage: css`
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    flex: 0 0 auto;
    padding-bottom: clamp(8px, 1.8vh, 12px);
    animation: ${emptyLogoFloat} 3.6s ease-in-out infinite;

    &::after {
      content: '';
      position: absolute;
      left: 50%;
      bottom: -2px;
      width: clamp(66px, 10vh, 96px);
      height: 16px;
      border-radius: 999px;
      background: var(--areqa-empty-logo-shadow);
      filter: blur(12px);
      animation: ${emptyLogoShadowPulse} 3.6s ease-in-out infinite;
      pointer-events: none;
    }

    html[data-interface-theme='light'] &::after {
      height: 20px;
      filter: blur(16px);
    }

    @media (prefers-reduced-motion: reduce) {
      animation: none;

      &::after {
        animation: none;
      }
    }
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
    width: clamp(88px, 14vh, 128px);
    height: auto;
    object-fit: contain;

    @media (max-width: 768px) {
      width: clamp(76px, 13vh, 96px);
    }
  `,

  emptyCopy: css`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    max-width: min(760px, 92vw);
    min-height: 3.8em;
  `,

  emptySubtitle: css`
    font-family: Georgia, Cambria, "Times New Roman", Times, serif;
    max-width: 100%;
    margin: 0;
    color: var(--areqa-message-muted-text);
    font-size: 1.35rem;
    font-weight: 600;
    letter-spacing: 0;
    line-height: 1.42;
    text-align: center;
    overflow-wrap: anywhere;

    .areqa-empty-typewriter-cursor {
      display: inline-block;
      width: 0.08em;
      height: 1em;
      margin-left: 0.08em;
      transform: translateY(0.12em);
      background: currentColor;
      animation: ${cursorBlink} 1s steps(1, end) infinite;
    }

    @media (max-width: 768px) {
      font-size: 1.08rem;
      line-height: 1.45;
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

  sourceFocusedMessage: css`
    border-radius: 12px;
    animation: ${sourceFocusPulse} 2.6s ease-out both;
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
    background: var(--areqa-user-bubble-background);
    color: var(--areqa-user-bubble-color);
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
    color: var(--areqa-message-text);
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
  color: var(--areqa-message-text);
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
    color: var(--areqa-message-muted-text);

    p {
      margin-bottom: 0;
    }
  }

  strong {
    color: var(--areqa-message-text);
    font-weight: 750;
  }

  em {
    color: var(--areqa-message-text);
  }

  code {
    padding: 0.14em 0.42em;
    border-radius: ${token.borderRadiusSM}px;
    background: color-mix(in srgb, var(--foreground) 9%, transparent);
    color: color-mix(in srgb, var(--areqa-message-text) 88%, #d8a25c);
    font-family: "SFMono-Regular", "Cascadia Code", "Liberation Mono", "Menlo", monospace;
    font-size: 0.88em;
    line-height: 1.65;
  }

  .areqa-markdown-code-frame {
    width: min(100%, 936px);
    margin: 14px 0;
    border: 1px solid color-mix(in srgb, var(--foreground) 10%, transparent);
    border-radius: 12px;
    background: color-mix(in srgb, var(--background) 88%, #ffffff 4%);
    box-shadow:
      inset 0 1px 0 color-mix(in srgb, var(--foreground) 6%, transparent),
      0 12px 26px rgba(0, 0, 0, 0.16);
    overflow: hidden;
  }

  .areqa-markdown-code-header {
    display: flex;
    min-height: 38px;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 0 14px;
    border-bottom: 1px solid color-mix(in srgb, var(--foreground) 8%, transparent);
    background: color-mix(in srgb, var(--foreground) 5%, transparent);
  }

  .areqa-markdown-code-language {
    overflow: hidden;
    color: var(--areqa-message-muted-text);
    font-family: "SFMono-Regular", "Cascadia Code", "Liberation Mono", "Menlo", monospace;
    font-size: 0.82em;
    font-weight: 600;
    line-height: 1;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .areqa-markdown-code-copy {
    display: inline-flex;
    width: 30px;
    height: 30px;
    flex: 0 0 30px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--areqa-message-muted-text);
    cursor: pointer;
    transition: background-color 120ms ease, color 120ms ease;

    &:hover {
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      color: var(--areqa-message-text);
    }

    &:focus-visible {
      outline: 2px solid rgba(216, 162, 92, 0.62);
      outline-offset: 2px;
    }
  }

  pre {
    margin: 0;
    padding: 16px 18px;
    background: transparent;
    overflow-x: auto;
    scrollbar-color: color-mix(in srgb, #d8a25c 72%, transparent) transparent;
    scrollbar-width: thin;

    code {
      padding: 0;
      background: transparent;
      color: var(--areqa-message-text);
      font-size: 0.92em;
      line-height: 1.7;
      white-space: pre;
    }

    &::-webkit-scrollbar {
      height: 8px;
    }

    &::-webkit-scrollbar-track {
      background: transparent;
    }

    &::-webkit-scrollbar-thumb {
      border-radius: 999px;
      background: color-mix(in srgb, #d8a25c 68%, transparent);
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

  [data-answer-block-index] + [data-answer-block-index],
  [data-live-answer-part] + [data-live-answer-part] {
    margin-top: 8px;
  }

  [data-answer-block-index] > :first-child,
  [data-live-answer-part] > :first-child {
    line-height: inherit;
  }

  a {
    color: ${token.colorLink};
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }

  .areqa-markdown-table-frame {
    position: relative;
    width: 100%;
    margin: 16px 0;
    border: 2px solid var(--areqa-table-border, rgba(156, 163, 175, 0.72));
    border-radius: 10px;
    background: var(--areqa-table-background, rgba(20, 20, 20, 0.98));
    overflow: hidden;
  }

  .areqa-markdown-table-actions {
    position: absolute;
    right: 8px;
    bottom: 8px;
    display: flex;
    align-items: center;
    height: 38px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    background: var(--areqa-table-action-background, rgba(18, 17, 16, 0.94));
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.36);
    opacity: 0;
    pointer-events: none;
    transform: translateY(4px);
    transition: opacity 140ms ease, transform 140ms ease;
  }

  .areqa-markdown-table-frame:hover .areqa-markdown-table-actions,
  .areqa-markdown-table-frame:focus-within .areqa-markdown-table-actions {
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0);
  }

  @media (hover: none) {
    .areqa-markdown-table-actions {
      opacity: 1;
      pointer-events: auto;
      transform: none;
    }
  }

  .areqa-markdown-table-action {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 42px;
    height: 38px;
    border: 0;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    background: transparent;
    color: var(--areqa-table-action-color, rgba(255, 255, 255, 0.62));
    line-height: 1;
    cursor: pointer;
    transition: background-color 120ms ease, color 120ms ease;

    &:hover {
      background: var(--areqa-table-action-hover, rgba(255, 255, 255, 0.07));
      color: var(--areqa-table-action-hover-color, #ffffff);
    }

    &:focus-visible {
      outline: 2px solid rgba(255, 255, 255, 0.42);
      outline-offset: -2px;
    }

    &:last-child {
      border-right: 0;
    }
  }

  .areqa-markdown-table-scroll {
    width: 100%;
    overflow-x: auto;
    outline: none;
    scrollbar-color: var(--areqa-table-scrollbar-thumb, rgba(255, 255, 255, 0.2)) transparent;
    scrollbar-width: thin;

    &:focus-visible {
      box-shadow: inset 0 0 0 2px rgba(209, 213, 219, 0.52);
    }
  }

  table.areqa-markdown-table {
    border-collapse: collapse;
    width: max-content;
    min-width: 100%;
    margin: 0;
    font-size: 15px;
    background: transparent;
  }

  .areqa-markdown-table th,
  .areqa-markdown-table td {
    min-width: 120px;
    padding: 12px 14px;
    border: 0;
    border-right: 2px solid var(--areqa-table-cell-border, rgba(156, 163, 175, 0.5));
    border-bottom: 2px solid var(--areqa-table-cell-border, rgba(156, 163, 175, 0.5));
    text-align: left;
    vertical-align: top;
  }

  .areqa-markdown-table th {
    border-bottom-color: var(--areqa-table-head-border, rgba(209, 213, 219, 0.68));
    background: var(--areqa-table-head-background, rgba(107, 114, 128, 0.42));
    color: var(--areqa-table-head-color, rgba(255, 255, 255, 0.98));
    font-weight: 700;
    white-space: nowrap;
  }

  .areqa-markdown-table td:first-child {
    font-weight: 700;
  }

  .areqa-markdown-table tbody tr {
    transition: background-color 120ms ease;
  }

  .areqa-markdown-table tbody tr:hover {
    background: var(--areqa-table-row-hover, rgba(255, 255, 255, 0.035));
  }

  .areqa-markdown-table tbody tr:last-child td {
    border-bottom: 0;
  }

  .areqa-markdown-table th:last-child,
  .areqa-markdown-table td:last-child {
    border-right: 0;
  }

  .areqa-markdown-table-modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 2200;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: clamp(18px, 6.8vh, 64px) clamp(18px, 7.4vw, 144px);
    background: rgba(0, 0, 0, 0.66);
    -webkit-backdrop-filter: blur(14px) saturate(108%);
    backdrop-filter: blur(14px) saturate(108%);
    animation: ${tableModalBackdropIn} 160ms ease-out;
  }

  .areqa-markdown-table-modal-panel {
    display: flex;
    flex-direction: column;
    width: min(1634px, 100%);
    height: min(742px, 100%);
    min-width: 0;
    min-height: min(420px, 100%);
    padding: 26px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    background: #141312;
    box-shadow: 0 30px 90px rgba(0, 0, 0, 0.64);
    animation: ${tableModalPanelIn} 180ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  .areqa-markdown-table-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    flex: 0 0 auto;
    margin-bottom: 30px;

    h2 {
      margin: 0;
      color: rgba(255, 255, 255, 0.88);
      font-size: 30px;
      font-weight: 700;
      line-height: 1.2;
    }
  }

  .areqa-markdown-table-modal-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 50px;
    height: 50px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 999px;
    background: transparent;
    color: rgba(255, 255, 255, 0.78);
    line-height: 1;
    cursor: pointer;
    transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;

    &:hover {
      background: rgba(255, 255, 255, 0.06);
      border-color: rgba(255, 255, 255, 0.18);
      color: #ffffff;
    }

    &:focus-visible {
      outline: 2px solid rgba(255, 255, 255, 0.42);
      outline-offset: 3px;
    }
  }

  .areqa-markdown-table-modal-body {
    flex: 0 1 auto;
    min-height: 0;
    max-height: 100%;
    overflow: auto;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    background: rgba(30, 29, 28, 0.98);
    outline: none;
    scrollbar-color: rgba(255, 255, 255, 0.22) transparent;
    scrollbar-width: thin;

    &:focus-visible {
      box-shadow: 0 0 0 2px rgba(209, 213, 219, 0.36);
    }

    table.areqa-markdown-table {
      width: max-content;
      min-width: 100%;
      font-size: 23px;
      color: rgba(255, 255, 255, 0.9);
    }

    .areqa-markdown-table th,
    .areqa-markdown-table td {
      min-width: 300px;
      padding: 14px 16px;
      border-right-width: 1px;
      border-bottom-width: 1px;
      border-right-color: rgba(255, 255, 255, 0.09);
      border-bottom-color: rgba(255, 255, 255, 0.08);
    }

    .areqa-markdown-table th {
      background: rgba(255, 255, 255, 0.045);
      border-bottom-color: rgba(255, 255, 255, 0.09);
      color: rgba(255, 255, 255, 0.98);
    }

    .areqa-markdown-table tbody tr:last-child td {
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
  }

  @media (max-width: 768px) {
    .areqa-markdown-table-modal-backdrop {
      padding: 14px;
    }

    .areqa-markdown-table-modal-panel {
      width: calc(100vw - 28px);
      height: calc(100vh - 28px);
      padding: 18px;
      border-radius: 14px;
    }

    .areqa-markdown-table-modal-header {
      margin-bottom: 18px;

      h2 {
        font-size: 24px;
      }
    }

    .areqa-markdown-table-modal-close {
      width: 44px;
      height: 44px;
    }

    .areqa-markdown-table-modal-body {
      min-height: 0;
      max-height: 100%;
    }

    table.areqa-markdown-table {
      font-size: 13px;
    }

    .areqa-markdown-table th,
    .areqa-markdown-table td {
      min-width: 104px;
      padding: 9px 10px;
    }

    .areqa-markdown-table-modal-body table.areqa-markdown-table {
      font-size: 16px;
    }

    .areqa-markdown-table-modal-body .areqa-markdown-table th,
    .areqa-markdown-table-modal-body .areqa-markdown-table td {
      min-width: 180px;
      padding: 11px 12px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .areqa-markdown-table-modal-backdrop,
    .areqa-markdown-table-modal-panel {
      animation: none;
    }
  }
`,

streamingContentReveal: css`
  position: relative;
  animation: ${verticalReveal} 260ms cubic-bezier(0.16, 1, 0.3, 1) both;

  @media (prefers-reduced-motion: reduce) {
    animation: none;
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



  streamingDots: css`
    display: inline-flex;
    align-items: center;
    gap: 7px;
    width: 38px;
    height: 1em;
    margin-left: 6px;
    vertical-align: -0.08em;
  `,

  streamingDot: css`
    width: 5px;
    height: 5px;
    border-radius: 999px;
    background: currentColor;
    opacity: 0.35;
    animation: ${streamingDotCycleStart} 5s ease-in-out infinite;

    &:nth-child(2) {
      animation-name: ${streamingDotCycleMiddle};
    }

    &:nth-child(3) {
      animation-name: ${streamingDotCycleEnd};
    }

    @media (prefers-reduced-motion: reduce) {
      animation: none;
      opacity: 0.75;
      transform: none;
    }
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
    border-radius: 0;
    background: transparent;
    animation: ${verticalReveal} 260ms cubic-bezier(0.16, 1, 0.3, 1) both;

    @media (prefers-reduced-motion: reduce) {
      animation: none;
    }
  `,

  answerImageExplanation: css`
    margin: 12px 0 10px;
    color: var(--areqa-message-text);
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
    color: var(--areqa-message-muted-text);
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
    color: var(--areqa-message-muted-text);
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
    color: var(--areqa-message-text);
    font-size: 13px;
    font-style: italic;
  `,

  answerImageMetaLine: css`
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    color: var(--areqa-message-muted-text);
    font-size: 12px;
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
    position: fixed;
    inset: 0;
    z-index: 2100;
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto;
    align-items: center;
    justify-items: center;
    width: 100vw;
    min-height: 100dvh;
    padding: max(20px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right))
      max(18px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left));
    background: rgba(18, 18, 18, 0.98);
    color: rgba(255, 255, 255, 0.9);
    animation: ${fadeIn} 160ms ease both;

    @media (max-width: 768px) {
      padding: max(14px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right))
        max(14px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left));
    }
  `,

  answerImageLightboxBack: css`
    position: fixed;
    top: max(22px, env(safe-area-inset-top));
    left: max(22px, env(safe-area-inset-left));
    z-index: 2;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    padding: 0;
    border: 0;
    border-radius: 999px;
    background: transparent;
    color: rgba(255, 255, 255, 0.78);
    cursor: pointer;
    transition: background 160ms ease, color 160ms ease;

    &:hover,
    &:focus-visible {
      background: rgba(255, 255, 255, 0.1);
      color: #ffffff;
      outline: none;
    }
  `,

  answerImageLightboxClose: css`
    position: fixed;
    top: max(22px, env(safe-area-inset-top));
    right: max(22px, env(safe-area-inset-right));
    z-index: 2;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    padding: 0;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.76);
    cursor: pointer;
    transition: background 160ms ease, color 160ms ease, border-color 160ms ease;

    &:hover,
    &:focus-visible {
      border-color: rgba(255, 255, 255, 0.26);
      background: rgba(255, 255, 255, 0.12);
      color: #ffffff;
      outline: none;
    }
  `,

  answerImageLightboxStage: css`
    display: flex;
    align-items: center;
    justify-content: center;
    width: min(100%, 76vw);
    min-height: 0;
    max-height: calc(100dvh - 118px);
    cursor: default;

    @media (max-width: 768px) {
      width: 100%;
      max-height: calc(100dvh - 148px);
    }
  `,

  answerImageLightboxImageLink: css`
    display: flex;
    align-items: center;
    justify-content: center;
    max-width: 100%;
    max-height: inherit;
    cursor: zoom-in;
  `,

  answerImageLightboxImage: css`
    display: block;
    max-width: 100%;
    max-height: inherit;
    width: auto;
    height: auto;
    object-fit: contain;
    border-radius: 0;
    background: #ffffff;
  `,

  answerImageLightboxMeta: css`
    justify-self: start;
    width: min(100%, 1180px);
    padding: 12px 18px 0;
    color: rgba(255, 255, 255, 0.72);
    font-size: 13px;
    font-style: italic;
    line-height: 1.55;

    p {
      max-width: min(100%, 980px);
      margin: 0 0 4px;
    }

    a {
      color: rgba(255, 255, 255, 0.88);
    }
  `,

  answerImageLightboxCaption: css`
    color: rgba(255, 255, 255, 0.86);
  `,

  answerImageLightboxSourceLine: css`
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    max-width: min(100%, 980px);
  `,

  answerImageLightboxSource: css`
    display: inline-flex;
    align-items: center;
    gap: 6px;
    width: fit-content;
    color: rgba(255, 255, 255, 0.9);
    text-decoration: none;

    &:hover {
      color: #ffffff;
      text-decoration: underline;
    }
  `,

  // Scroll to bottom button
  scrollButton: css`
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    width: 48px;
    height: 48px;
    min-width: 48px;
    min-height: 48px;
    box-sizing: border-box;
    border-radius: 50%;
    background: rgba(18, 18, 20, 0.88);
    color: rgba(255, 255, 255, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.16);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow:
      0 12px 28px rgba(0, 0, 0, 0.28),
      inset 0 1px 0 rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(14px);
    transition:
      background 0.18s ease,
      border-color 0.18s ease,
      color 0.18s ease,
      box-shadow 0.18s ease,
      transform 0.18s ease;
    z-index: 30;

    @media (max-width: 768px) {
      bottom: max(16px, env(safe-area-inset-bottom));
      width: 52px;
      height: 52px;
      min-width: 52px;
      min-height: 52px;
    }

    &:hover {
      background: rgba(28, 28, 31, 0.94);
      border-color: rgba(255, 255, 255, 0.24);
      color: #ffffff;
      transform: translateX(-50%) translateY(-1px);
      box-shadow:
        0 16px 32px rgba(0, 0, 0, 0.34),
        inset 0 1px 0 rgba(255, 255, 255, 0.12);
    }

    &:active {
      transform: translateX(-50%) translateY(0) scale(0.96);
      background: rgba(10, 10, 12, 0.96);
    }

    &:focus-visible {
      outline: 2px solid rgba(255, 255, 255, 0.72);
      outline-offset: 3px;
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
    color: var(--areqa-message-action-color);
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      color: var(--areqa-message-action-hover-color);
      background: var(--areqa-message-action-hover-background);
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
    color: var(--areqa-message-action-color);
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      color: var(--areqa-message-action-hover-color);
      background: var(--areqa-message-action-hover-background);
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
    min-height: 4.5em;
    padding: 0;
    border: 0;
    border-radius: 0;
    font-size: 16px;
    line-height: 1.8;
    resize: none;
    outline: none;
    font-family: inherit;
    background: transparent;
    color: var(--areqa-message-text);
    overflow: hidden;
    overflow-wrap: anywhere;
    word-break: break-word;

    &::placeholder {
      color: var(--areqa-message-muted-text);
    }
  `,

  assistantEditSurface: css`
    width: 100%;
    min-width: 0;
    align-self: stretch;
    box-sizing: border-box;
    box-shadow: inset 0 -1px 0 rgba(216, 162, 92, 0.28);
  `,

  richEditSurface: css`
    position: relative;
    width: 100%;
    min-height: 4.5em;
    color: var(--areqa-message-text);

    [contenteditable='true'],
    [contenteditable='false'] {
      width: 100%;
      min-height: 4.5em;
      outline: none;
      font-size: 16px;
      line-height: 1.8;
      overflow-wrap: anywhere;
      word-break: break-word;
    }

    [contenteditable='false'] {
      opacity: 0.62;
      cursor: progress;
    }

    p,
    blockquote,
    ul,
    ol,
    table,
    figure,
    pre {
      margin-top: 0;
    }

    p {
      margin: 0 0 8px;
    }

    h1,
    h2,
    h3,
    h4 {
      margin: 10px 0 8px;
      color: var(--areqa-message-text);
      font-weight: 720;
      line-height: 1.35;
    }

    h1 {
      font-size: 1.45rem;
    }

    h2 {
      font-size: 1.25rem;
    }

    h3,
    h4 {
      font-size: 1.08rem;
    }

    ul,
    ol {
      padding-left: 1.55rem;
      margin-bottom: 10px;
    }

    li {
      margin: 2px 0;
    }

    li[data-depth='1'] {
      margin-left: 1.4rem;
    }

    li[data-depth='2'],
    li[data-depth='3'],
    li[data-depth='4'] {
      margin-left: 2.8rem;
    }

    blockquote {
      margin-bottom: 10px;
      padding: 2px 0 2px 16px;
      border-left: 3px solid rgba(255, 255, 255, 0.25);
      color: var(--areqa-message-muted-text);
    }

    table {
      width: 100%;
      margin: 12px 0 14px;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th,
    td {
      min-width: 84px;
      padding: 8px 10px;
      border: 1px solid color-mix(in srgb, var(--foreground) 22%, transparent);
      vertical-align: top;
    }

    th {
      background: color-mix(in srgb, var(--foreground) 6%, transparent);
      font-weight: 700;
    }

    figure {
      margin: 14px 0;
    }

    img {
      display: block;
      max-width: 100%;
      max-height: 460px;
      border-radius: 6px;
      object-fit: contain;
    }

    figcaption {
      margin-top: 6px;
      color: var(--areqa-message-muted-text);
      font-size: 12px;
      line-height: 1.45;
    }

    code {
      padding: 0.14em 0.42em;
      border-radius: ${token.borderRadiusSM}px;
      background: color-mix(in srgb, var(--foreground) 9%, transparent);
      color: color-mix(in srgb, var(--areqa-message-text) 88%, #d8a25c);
      font-family: "SFMono-Regular", "Cascadia Code", "Liberation Mono", "Menlo", monospace;
      font-size: 0.88em;
    }

    pre {
      margin-bottom: 12px;
      padding: 10px 12px;
      border-radius: 6px;
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      overflow-x: auto;
      white-space: pre-wrap;
    }

    pre code {
      display: block;
      padding: 0;
      background: transparent;
      white-space: pre-wrap;
    }
  `,

  richEditSlashMenu: css`
    position: absolute;
    z-index: 2;
    left: 0;
    top: 0;
    width: min(304px, calc(100vw - 48px));
    max-height: 344px;
    overflow-y: auto;
    padding: 8px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    background: #1b1b1d;
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.34);
  `,

  richEditSlashMenuItem: css`
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    min-height: 36px;
    padding: 7px 9px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: rgba(255, 255, 255, 0.82);
    cursor: pointer;
    font: inherit;
    font-size: 13px;
    text-align: left;

    &:hover,
    &:focus-visible {
      background: rgba(216, 162, 92, 0.16);
      color: #ffffff;
      outline: none;
    }

    svg {
      flex: 0 0 auto;
      color: #d8a25c;
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
