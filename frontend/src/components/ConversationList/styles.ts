/**
 * ConversationList Styles
 * CSS-in-JS styles using antd-style
 */

import { createStyles, keyframes } from 'antd-style';

const cursorBlink = keyframes`
  from,
  to {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
`;

export const useStyles = createStyles(({ css }) => ({
  container: css`
    display: flex;
    flex-direction: column;
    height: 100%;
    background: #2d2d2d;
    color: #f0f0f0;
  `,

  header: css`
    padding: 4px 16px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  `,

  logoContainer: css`
    padding: 12px 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  `,

  logoWrapper: css`
    display: flex;
    align-items: center;
    justify-content: flex-start;
    flex: 1;
    min-width: 0;
  `,

  logo: css`
    width: 210px;
    height: auto;
    object-fit: contain;
    flex-shrink: 0;
  `,

  toggleButton: css`
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.4);
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.2s;
    flex-shrink: 0;

    &:hover {
      background: rgba(255, 255, 255, 0.05);
      color: #ffffff;
    }
  `,

  title: css`
    font-size: 14px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.45);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  `,

  newButton: css`
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 10px;
    width: 100%;
    padding: 10px 16px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.2);
    }

    svg {
      color: #FF4D4D;
    }
  `,

  list: css`
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;

    /* Hide scrollbar */
    &::-webkit-scrollbar {
      display: none;
    }
    -ms-overflow-style: none;  /* IE and Edge */
    scrollbar-width: none;  /* Firefox */
  `,

  groupTitle: css`
    font-size: 14px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.5);
    padding: 20px 12px 10px;
    letter-spacing: 0.3px;
  `,

  item: css`
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    user-select: none;
    margin-bottom: 2px;

    &:hover {
      background: rgba(255, 255, 255, 0.05);
      
      .delete-btn {
        opacity: 1;
      }
    }
  `,

  itemActive: css`
    background: rgba(168, 34, 34, 0.25) !important;
    
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 20%;
      height: 60%;
      width: 3px;
      background: #A82222;
      border-radius: 0 2px 2px 0;
    }

    .conv-title {
      color: #ffffff;
      font-weight: 500;
    }
  `,

  itemIcon: css`
    color: rgba(255, 255, 255, 0.4);
    flex-shrink: 0;
  `,

  itemContent: css`
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  `,

  itemTitle: css`
    font-size: 14px;
    color: rgba(255, 255, 255, 0.85);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: color 0.2s;
  `,

  cursor: css`
    display: inline-block;
    width: 2px;
    height: 14px;
    background: #A82222;
    margin-left: 2px;
    vertical-align: middle;
    animation: ${cursorBlink} 1s step-end infinite;
  `,

  deleteBtn: css`
    opacity: 0;
    padding: 4px;
    border-radius: 4px;
    color: rgba(255, 255, 255, 0.3);
    transition: all 0.2s;
    flex-shrink: 0;

    &:hover {
      color: #ff4d4f;
      background: rgba(255, 77, 79, 0.1);
    }
  `,

  loading: css`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 20px;
  `,

  empty: css`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px 20px;
    text-align: center;
    opacity: 0.5;
  `,

  emptyIcon: css`
    margin-bottom: 12px;
    color: rgba(255, 255, 255, 0.2);
  `,

  emptyText: css`
    font-size: 13px;
    color: rgba(255, 255, 255, 0.4);
    line-height: 1.6;
  `,
}));
