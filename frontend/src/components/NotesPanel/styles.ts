import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css, token }) => ({
  panel: css`
    position: relative;
    display: flex;
    width: 100%;
    height: 100%;
    min-height: 0;
    flex-direction: column;
    background: var(--background);
    color: var(--foreground);
  `,
  closeButton: css`
    position: absolute;
    top: 18px;
    right: 22px;
    z-index: 2;
    display: inline-flex;
    width: 36px;
    height: 36px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--background) 88%, transparent);
    color: ${token.colorTextSecondary};
    cursor: pointer;

    &:hover {
      background: ${token.colorFillTertiary};
      color: ${token.colorText};
    }
  `,
  content: css`
    display: flex;
    min-height: 0;
    flex: 1;
    flex-direction: column;
    gap: 18px;
    overflow-y: auto;
    padding: 32px min(5vw, 48px);
  `,
  header: css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding-right: 52px;
  `,
  titleRow: css`
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 10px;

    svg {
      color: #d8a25c;
      flex: 0 0 auto;
    }

    h2 {
      margin: 0;
      overflow: hidden;
      color: var(--foreground);
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  `,
  actionButton: css`
    display: inline-flex;
    min-height: 34px;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 8px;
    background: transparent;
    color: var(--foreground);
    cursor: pointer;
    padding: 0 12px;
    font-size: 14px;

    &:hover:not(:disabled) {
      background: ${token.colorFillTertiary};
    }

    &:disabled {
      cursor: progress;
      opacity: 0.6;
    }
  `,
  searchInput: css`
    max-width: 520px;
  `,
  empty: css`
    display: flex;
    min-height: 220px;
    align-items: center;
    justify-content: center;
    color: var(--muted-foreground);
    text-align: center;
  `,
  list: css`
    display: flex;
    flex-direction: column;
    gap: 12px;
  `,
  noteCard: css`
    display: flex;
    flex-direction: column;
    gap: 12px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--foreground) 4%, transparent);
    padding: 16px;
  `,
  noteMeta: css`
    display: flex;
    min-width: 0;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    color: var(--muted-foreground);
    font-size: 13px;
  `,
  noteSource: css`
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  `,
  noteBody: css`
    color: var(--areqa-message-text);
    font-size: 15px;
    line-height: 1.75;
    white-space: pre-wrap;
  `,
  noteTools: css`
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  `,
}));
