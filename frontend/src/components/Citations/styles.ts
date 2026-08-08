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
      background: rgba(255, 255, 255, 0.5);
      border-radius: 4px;
    }
    &::-webkit-scrollbar-track {
      background: rgba(255, 255, 255, 0.05);
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
    background: #1e1826;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: ${token.borderRadiusLG}px;
    transition: all 0.2s;
    cursor: pointer;

    &:hover {
      background: #282133;
      border-color: rgba(255, 255, 255, 0.2);
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
    color: #ffffff;
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
      color: #ffffff;
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,

  sourceSnippet: css`
    font-size: 15px;
    color: rgba(255, 255, 255, 0.7);
    line-height: 1.6;
    
    // Clamp to 3 lines
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;

    p,
    ul,
    ol,
    blockquote {
      margin: 0;
    }

    ul,
    ol {
      padding-left: 18px;
    }

    strong {
      color: rgba(255, 255, 255, 0.88);
      font-weight: 700;
    }

    em {
      color: rgba(255, 255, 255, 0.82);
    }

    code {
      padding: 1px 4px;
      border-radius: ${token.borderRadiusXS}px;
      background: rgba(255, 255, 255, 0.08);
      color: rgba(255, 255, 255, 0.9);
      font-size: 0.92em;
    }

    a {
      color: #8cc8ff;
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,

  modalSourceTitle: css`
    margin: 0;
    color: #ffffff;
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
      color: #ffffff;
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,

  modalSourceSnippet: css`
    position: relative;
    z-index: 1;
    color: #f0f0f0;
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
    }

    blockquote {
      margin: 0 0 10px;
      padding-left: 12px;
      border-left: 3px solid rgba(255, 77, 79, 0.5);
      color: rgba(255, 255, 255, 0.82);
    }

    strong {
      color: #ffffff;
      font-weight: 700;
    }

    code {
      padding: 2px 5px;
      border-radius: ${token.borderRadiusXS}px;
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
      font-size: 0.92em;
    }

    a {
      color: #8cc8ff;
      text-decoration: underline;
      text-underline-offset: 2px;
    }
  `,
}));
