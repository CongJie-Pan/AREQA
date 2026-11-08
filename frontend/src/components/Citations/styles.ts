/**
 * Citations Styles
 * CSS-in-JS styles using antd-style
 */

import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css, token }) => ({
  container: css`
    margin-top: 12px;
  `,

  header: css`
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 0;
    cursor: pointer;
    user-select: none;
    color: ${token.colorTextSecondary};
    font-size: 15px;
    font-weight: 600;

    &:hover {
      color: ${token.colorText};
    }
  `,

  icon: css`
    color: ${token.colorTextTertiary};
    transition: transform 0.2s ${token.motionEaseOut};
  `,

  iconExpanded: css`
    transform: rotate(90deg);
  `,

  count: css`
    color: ${token.colorTextQuaternary};
    font-size: 13px;
  `,

  list: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding-left: 20px;
  `,

  link: css`
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border-radius: ${token.borderRadius}px;
    font-size: 13px;
    color: ${token.colorLink};
    text-decoration: none;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    transition: all 0.2s;

    &:hover {
      background: ${token.colorFillQuaternary};
      color: ${token.colorLinkHover};
    }
  `,

  linkIcon: css`
    flex-shrink: 0;
    color: ${token.colorTextQuaternary};
  `,

  linkNumber: css`
    flex-shrink: 0;
    min-width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: ${token.borderRadiusSM}px;
    background: ${token.colorFillTertiary};
    color: ${token.colorTextSecondary};
    font-size: 11px;
    font-weight: 500;
  `,

  linkText: css`
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  `,

  sourcesGrid: css`
    display: flex;
    overflow-x: auto;
    gap: 10px;
    padding: 6px 2px 8px 2px;
    width: 100%;
    min-width: 0;

    // Smooth scrolling & hide scrollbar for webkit
    /* Scrollbar styling */
    &::-webkit-scrollbar {
      height: 6px;
    }
    &::-webkit-scrollbar-thumb {
      background: color-mix(in srgb, var(--foreground) 50%, transparent);
      border-radius: 4px;
    }
    &::-webkit-scrollbar-track {
      background: color-mix(in srgb, var(--foreground) 5%, transparent);
      border-radius: 4px;
    }
    `,

  sourceCard: css`
    box-sizing: border-box;
    flex: 0 0 280px;
    width: 280px;
    min-width: 280px;
    max-width: 280px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    background: var(--card);
    border: 1px solid color-mix(in srgb, var(--foreground) 10%, transparent);
    border-radius: ${token.borderRadiusLG}px;
    transition: all 0.2s;
    cursor: pointer;

    &:hover {
      background: var(--muted);
      border-color: color-mix(in srgb, var(--foreground) 20%, transparent);
    }
  `,

  sourceHeader: css`
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  `,

  sourceTitle: css`
    flex: 1 1 auto;
    min-width: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--foreground);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    p {
      margin: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    strong {
      font-weight: 700;
    }

    a {
      color: var(--foreground);
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,

  sourceSnippetFrame: css`
    max-height: calc(15px * 1.6 * 3);
    overflow: hidden;
    mask-image: linear-gradient(to bottom, #000 78%, transparent 100%);
  `,

  sourceSnippet: css`
    font-size: 15px;
    color: color-mix(in srgb, var(--foreground) 70%, transparent);
    line-height: 1.6;

    p,
    blockquote {
      margin: 0;
    }

    p + p,
    p + ul,
    p + ol,
    ul + p,
    ol + p {
      margin-top: 4px;
    }

    ul,
    ol {
      display: block;
      margin: 0;
      padding-left: 22px;
      list-style-position: outside;
    }

    ul {
      list-style-type: disc;
    }

    ol {
      list-style-type: decimal;
    }

    li {
      display: list-item;
      padding-left: 2px;
    }

    li::marker {
      color: color-mix(in srgb, var(--foreground) 62%, transparent);
      font-weight: 600;
    }

    strong {
      color: color-mix(in srgb, var(--foreground) 88%, transparent);
      font-weight: 700;
    }

    em {
      color: color-mix(in srgb, var(--foreground) 82%, transparent);
    }

    code {
      padding: 1px 4px;
      border-radius: ${token.borderRadiusXS}px;
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      color: color-mix(in srgb, var(--foreground) 90%, transparent);
      font-size: 0.92em;
    }

    a {
      color: ${token.colorLink};
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,

  modalSourceTitle: css`
    margin: 0;
    color: var(--foreground);
    font-size: 20px;
    font-weight: 600;
    line-height: 1.45;

    p {
      margin: 0;
    }

    strong {
      font-weight: 700;
    }

    a {
      color: var(--foreground);
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,

  modalSourceSnippet: css`
    position: relative;
    z-index: 1;
    color: var(--foreground);
    font-size: 16px;
    line-height: 1.8;

    p {
      margin: 0 0 10px;
    }

    p:last-child,
    ul:last-child,
    ol:last-child,
    blockquote:last-child {
      margin-bottom: 0;
    }

    ul,
    ol {
      margin: 0 0 10px;
      padding-left: 22px;
      list-style-position: outside;
    }

    ul {
      list-style-type: disc;
    }

    ol {
      list-style-type: decimal;
    }

    li {
      display: list-item;
      padding-left: 2px;
    }

    li::marker {
      color: color-mix(in srgb, var(--foreground) 72%, transparent);
      font-weight: 600;
    }

    blockquote {
      margin: 0 0 10px;
      padding-left: 12px;
      border-left: 3px solid rgba(255, 77, 79, 0.5);
      color: color-mix(in srgb, var(--foreground) 82%, transparent);
    }

    strong {
      color: var(--foreground);
      font-weight: 700;
    }

    code {
      padding: 2px 5px;
      border-radius: ${token.borderRadiusXS}px;
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      color: var(--foreground);
      font-size: 0.92em;
    }

    a {
      color: ${token.colorLink};
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,
}));
