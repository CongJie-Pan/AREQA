import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({
  panel: css`
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    background: #130f18;
  `,
  header: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 24px 32px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(19, 15, 24, 0.6);
    backdrop-filter: blur(12px);
    z-index: 10;
  `,
  titleWrapper: css`
    display: flex;
    align-items: center;
    gap: 16px;
    h2 {
      margin: 0;
      color: #fff;
      font-size: 1.35rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: linear-gradient(90deg, #fff, #aaa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    p {
      margin: 6px 0 0;
      color: rgba(255, 255, 255, 0.5);
      font-size: 0.85rem;
    }
  `,
  closeBtn: css`
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #aaa;
    cursor: pointer;
    padding: 10px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    &:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #fff;
      transform: scale(1.05);
    }
    &:active {
      transform: scale(0.95);
    }
  `,
  content: css`
    flex: 1;
    overflow-y: auto;
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    
    &::-webkit-scrollbar {
      width: 6px;
    }
    &::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 4px;
    }
    &::-webkit-scrollbar-track {
      background: transparent;
    }
  `,
  // ListView Styles
  listRow: css`
    display: flex;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    cursor: pointer;
    transition: all 0.2s ease;
    background: rgba(30, 24, 38, 0.2);

    &:hover {
      background: rgba(255, 255, 255, 0.05);
      box-shadow: inset 1px 0 0 #d8a25c;
    }
    
    &.unread {
      background: rgba(216, 162, 92, 0.05);
      font-weight: 600;
      color: #fff;
    }
  `,
  rowSender: css`
    flex: 0 0 140px;
    font-size: 0.95rem;
    color: rgba(255, 255, 255, 0.9);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-align: center;
  `,
  rowSnippet: css`
    flex: 1;
    font-size: 0.9rem;
    color: rgba(255, 255, 255, 0.6);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0 16px;
    
    .unread & {
      color: rgba(255, 255, 255, 0.9);
    }
  `,
  rowDate: css`
    flex: 0 0 80px;
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.4);
    text-align: right;
  `,
  
  // Thread Detail View Styles
  threadHeader: css`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  `,
  backBtn: css`
    background: transparent;
    border: none;
    color: #aaa;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    border-radius: 50%;
    transition: all 0.2s ease;
    &:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #fff;
    }
  `,
  threadTitle: css`
    font-size: 1.2rem;
    font-weight: 600;
    color: #fff;
  `,
  messageItem: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 24px;
    
    &.user {
      align-items: flex-end;
    }
  `,
  messageBubble: css`
    max-width: 85%;
    padding: 16px 20px;
    border-radius: 16px;
    font-size: 0.95rem;
    line-height: 1.6;
    letter-spacing: 0.2px;
    word-break: break-word;
    white-space: pre-wrap;
    
    background: rgba(30, 24, 38, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.05);
    color: rgba(255, 255, 255, 0.9);
    border-bottom-left-radius: 4px;
    
    .user & {
      background: rgba(216, 162, 92, 0.15);
      border: 1px solid rgba(216, 162, 92, 0.3);
      border-bottom-left-radius: 16px;
      border-bottom-right-radius: 4px;
    }
  `,
  messageMeta: css`
    font-size: 0.8rem;
    color: rgba(255, 255, 255, 0.4);
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 4px;
  `,
  replyBox: css`
    margin-top: 32px;
    padding: 24px;
    background: rgba(0, 0, 0, 0.2);
    border: 1px dashed rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  `,
  emptyState: css`
    text-align: center;
    padding: 60px 20px;
    color: rgba(255, 255, 255, 0.4);
    font-size: 1rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
  `,
}));
