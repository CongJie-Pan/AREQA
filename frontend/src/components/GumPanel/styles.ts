import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({
  panel: css`
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    background: linear-gradient(145deg, #111 0%, #1a1a1a 100%);
  `,
  header: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 24px 32px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(20, 20, 20, 0.6);
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
  card: css`
    background: rgba(35, 35, 35, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 16px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    flex-shrink: 0;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    backdrop-filter: blur(8px);
    position: relative;
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
      background: transparent;
      transition: background 0.3s ease;
    }

    &:hover {
      background: rgba(45, 45, 45, 0.6);
      border-color: rgba(255, 255, 255, 0.15);
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    }
    
    &.selected {
      background: rgba(245, 158, 11, 0.05);
      border-color: rgba(245, 158, 11, 0.3);
      &::before {
        background: #f59e0b;
      }
    }
  `,
  cardText: css`
    color: rgba(255, 255, 255, 0.9);
    font-size: 0.95rem;
    line-height: 1.6;
    letter-spacing: 0.2px;
    word-break: break-word;
    white-space: pre-wrap;
  `,
  cardMeta: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: rgba(255, 255, 255, 0.4);
    font-size: 0.8rem;
    margin-top: 4px;
  `,
  confidenceBadge: css`
    display: inline-block;
    background: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    padding: 4px 10px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 0.75rem;
    letter-spacing: 0.5px;
    border: 1px solid rgba(245, 158, 11, 0.2);
  `,
  suggestionTitle: css`
    color: #fff;
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
    &::before {
      content: '';
      display: block;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #f59e0b;
    }
  `,
  refreshBtn: css`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 500;
    transition: all 0.2s ease;
    &:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #fff;
    }
    &:active {
      transform: scale(0.96);
    }
    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `,
}));
