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
  filters: css`
    display: flex;
    flex-direction: column;
    gap: 10px;
  `,
  filterGroup: css`
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  `,
  filterChip: css`
    display: inline-flex;
    min-height: 30px;
    max-width: 220px;
    align-items: center;
    gap: 6px;
    overflow: hidden;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 999px;
    background: transparent;
    color: var(--muted-foreground);
    cursor: pointer;
    padding: 0 11px;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;

    span {
      color: ${token.colorTextTertiary};
      font-size: 12px;
    }

    &:hover {
      background: ${token.colorFillTertiary};
      color: var(--foreground);
    }
  `,
  filterChipActive: css`
    display: inline-flex;
    min-height: 30px;
    max-width: 220px;
    align-items: center;
    gap: 6px;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, #d8a25c 68%, transparent);
    border-radius: 999px;
    background: color-mix(in srgb, #d8a25c 14%, transparent);
    color: var(--foreground);
    cursor: pointer;
    padding: 0 11px;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  `,
  empty: css`
    display: flex;
    min-height: 220px;
    align-items: center;
    justify-content: center;
    color: var(--muted-foreground);
    text-align: center;
  `,
  groupList: css`
    display: flex;
    flex-direction: column;
    gap: 14px;
  `,
  group: css`
    display: flex;
    flex-direction: column;
    gap: 10px;
  `,
  groupHeader: css`
    display: flex;
    min-height: 38px;
    align-items: center;
    gap: 8px;
    border: 0;
    border-bottom: 1px solid var(--areqa-subtle-border);
    background: transparent;
    color: var(--foreground);
    cursor: pointer;
    padding: 0 2px 8px;
    text-align: left;

    span {
      flex: 1;
      font-size: 15px;
      font-weight: 700;
    }

    strong {
      color: var(--muted-foreground);
      font-size: 13px;
      font-weight: 600;
    }
  `,
  list: css`
    display: flex;
    flex-direction: column;
    gap: 10px;
  `,
  noteCard: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--foreground) 4%, transparent);
    padding: 12px 14px;
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
    line-height: 1.6;
    white-space: pre-wrap;
  `,
  latinText: css`
    font-family: "Times New Roman", Times, serif;
  `,
  inlineButton: css`
    width: fit-content;
    border: 0;
    background: transparent;
    color: #b7793a;
    cursor: pointer;
    padding: 0;
    font-size: 13px;
    font-weight: 600;

    &:hover {
      color: #d8a25c;
      text-decoration: underline;
    }
  `,
  tagEditor: css`
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  `,
  tagChip: css`
    display: inline-flex;
    min-height: 28px;
    max-width: 180px;
    align-items: center;
    gap: 5px;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, #d8a25c 46%, transparent);
    border-radius: 999px;
    background: color-mix(in srgb, #d8a25c 10%, transparent);
    color: var(--foreground);
    cursor: pointer;
    padding: 0 9px;
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;

    &:hover {
      border-color: color-mix(in srgb, #d8a25c 74%, transparent);
      background: color-mix(in srgb, #d8a25c 16%, transparent);
    }
  `,
  tagInput: css`
    width: 128px;
    min-width: 104px;
  `,
  noteTools: css`
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 6px;
  `,
  iconActionButton: css`
    display: inline-flex;
    width: 34px;
    height: 34px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--areqa-subtle-border);
    border-radius: 8px;
    background: transparent;
    color: var(--foreground);
    cursor: pointer;

    &:hover {
      background: ${token.colorFillTertiary};
    }
  `,
}));
