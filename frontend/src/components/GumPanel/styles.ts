import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({

  panel: css`
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    animation: fadeIn 0.3s ease-out;
  `,
  header: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid #333;
  `,
  titleWrapper: css`
    display: flex;
    align-items: center;
    gap: 12px;
    h2 {
      margin: 0;
      color: #fff;
      font-size: 1.25rem;
      font-weight: 600;
    }
    p {
      margin: 4px 0 0;
      color: #888;
      font-size: 0.875rem;
    }
  `,
  closeBtn: css`
    background: transparent;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 8px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    &:hover {
      background: #333;
      color: #fff;
    }
  `,
  content: css`
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  `,
  card: css`
    background: #252525;
    border: 1px solid #333;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: all 0.2s;
    &:hover {
      border-color: #555;
    }
  `,
  cardText: css`
    color: #e5e5e5;
    font-size: 0.95rem;
    line-height: 1.5;
  `,
  cardMeta: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #888;
    font-size: 0.8rem;
  `,
  confidenceBadge: css`
    background: rgba(245, 158, 11, 0.1);
    color: #f59e0b;
    padding: 2px 8px;
    border-radius: 12px;
    font-weight: 500;
  `,
  suggestionTitle: css`
    color: #fff;
    font-size: 1.05rem;
    font-weight: 600;
    margin-bottom: 4px;
  `,
  refreshBtn: css`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 8px;
    color: #e5e5e5;
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s;
    &:hover {
      background: #333;
    }
    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `,
}));
