import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css, token }) => ({
  panel: css`
    --areqa-memory-accent: color-mix(in srgb, ${token.colorWarningText} 45%, var(--foreground));
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    animation: fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    background: var(--background);
    color: var(--foreground);
    position: relative;
  `,
  accentIcon: css`
    color: var(--areqa-memory-accent);
  `,
  closeBtnFixed: css`
    position: absolute;
    top: 24px;
    right: 32px;
    background: color-mix(in srgb, var(--foreground) 4%, transparent);
    border: 1px solid color-mix(in srgb, var(--foreground) 10%, transparent);
    color: var(--muted-foreground);
    cursor: pointer;
    padding: 10px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    z-index: 50;
    &:hover {
      background: color-mix(in srgb, var(--foreground) 10%, transparent);
      color: var(--foreground);
      transform: scale(1.05);
    }
    &:active {
      transform: scale(0.95);
    }
  `,
  content: css`
    flex: 1;
    overflow-y: auto;
    padding: 40px 32px;
    display: flex;
    flex-direction: column;
    gap: 32px;
    
    @media (max-width: 768px) {
      padding: 24px 16px;
      gap: 24px;
    }
    
    &::-webkit-scrollbar {
      width: 6px;
    }
    &::-webkit-scrollbar-thumb {
      background: color-mix(in srgb, var(--foreground) 10%, transparent);
      border-radius: 4px;
    }
    &::-webkit-scrollbar-track {
      background: transparent;
    }
  `,
  heroSection: css`
    background: linear-gradient(145deg, var(--card), var(--muted));
    border: 1px solid color-mix(in srgb, var(--foreground) 8%, transparent);
    border-radius: 20px;
    padding: 24px;
    display: flex;
    flex-shrink: 0;
    flex-direction: column;
    gap: 16px;
    box-shadow: ${token.boxShadowSecondary};
    position: relative;
    overflow: hidden;

    @media (max-width: 768px) {
      padding: 16px;
    }
    &::before {
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle at center, rgba(212, 175, 55, 0.05) 0%, transparent 50%);
      pointer-events: none;
    }
  `,
  heroTitleRow: css`
    display: flex;
    align-items: center;
    gap: 12px;
    h2 {
      margin: 0;
      color: var(--foreground);
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: 0.5px;
    }
  `,
  heroSummaryBox: css`
    background: rgba(212, 175, 55, 0.04);
    border: 1px solid rgba(212, 175, 55, 0.15);
    border-radius: 12px;
    padding: 16px 20px;
    color: var(--foreground);
    font-size: 0.95rem;
    line-height: 1.6;
    ul {
      margin: 12px 0 0 0;
      padding-left: 20px;
      color: var(--muted-foreground);
      li {
        margin-bottom: 4px;
      }
    }
  `,
  heroHashtag: css`
    display: inline-block;
    background: rgba(212, 175, 55, 0.15);
    color: var(--areqa-memory-accent);
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;
    margin-right: 8px;
    margin-top: 12px;
    border: 1px solid rgba(212, 175, 55, 0.3);
  `,
  sectionHeader: css`
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    h3 {
      margin: 0;
      color: var(--foreground);
      font-size: 1.1rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    span {
      color: var(--muted-foreground);
      font-size: 0.9rem;
      font-weight: 400;
    }
  `,
  assetsGrid: css`
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 16px;
  `,
  assetCard: css`
    background: var(--card);
    border: 1px solid color-mix(in srgb, var(--foreground) 6%, transparent);
    border-radius: 16px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: all 0.3s ease;
    &:hover {
      background: color-mix(in srgb, var(--foreground) 5%, transparent);
      border-color: rgba(212, 175, 55, 0.3);
      transform: translateY(-2px);
    }
  `,
  assetLabel: css`
    color: var(--muted-foreground);
    font-size: 0.85rem;
  `,
  assetValue: css`
    color: var(--foreground);
    font-size: 1.5rem;
    font-weight: 700;
    span {
      font-size: 0.85rem;
      color: var(--muted-foreground);
      font-weight: 400;
      margin-left: 4px;
    }
  `,
  timelineSection: css`
    display: flex;
    flex-direction: column;
  `,
  timelineHeaderRow: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

    @media (max-width: 768px) {
      flex-direction: column;
      align-items: flex-start;
      gap: 16px;
    }
  `,
  timelineActions: css`
    display: flex;
    align-items: center;
    gap: 12px;
  `,
  timelineGroup: css`
    margin-bottom: 32px;
  `,
  timelineDate: css`
    color: var(--foreground);
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    &::after {
      content: '';
      flex: 1;
      height: 1px;
      background: color-mix(in srgb, var(--foreground) 8%, transparent);
      margin-top: 2px;
    }
  `,
  timelineItems: css`
    display: flex;
    flex-direction: column;
  `,
  timelineItem: css`
    display: flex;
    gap: 16px;
    padding: 16px 0;
    border-bottom: 1px dashed color-mix(in srgb, var(--foreground) 8%, transparent);
    position: relative;
    transition: all 0.2s ease;

    @media (max-width: 768px) {
      gap: 8px;
    }
    &:last-child {
      border-bottom: none;
    }
    &:hover {
      background: color-mix(in srgb, var(--foreground) 2%, transparent);
      border-radius: 8px;
      padding-left: 8px;
      padding-right: 8px;
      margin: 0 -8px;
      .timelineTools {
        opacity: 1;
        pointer-events: auto;
      }
    }
  `,
  timelineTimeBox: css`
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    width: 60px;
    flex-shrink: 0;
    padding-top: 4px;

    @media (max-width: 768px) {
      width: 45px;
    }
  `,
  timelineTime: css`
    color: var(--muted-foreground);
    font-size: 0.85rem;
    font-family: monospace;
  `,
  timelineTag: css`
    background: color-mix(in srgb, var(--foreground) 6%, transparent);
    color: var(--muted-foreground);
    font-size: 0.7rem;
    padding: 2px 6px;
    border-radius: 4px;
    white-space: nowrap;
  `,
  timelineContent: css`
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 2px;
  `,
  timelineText: css`
    color: var(--foreground);
    font-size: 0.95rem;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  `,
  timelineTools: css`
    opacity: 0;
    pointer-events: none;
    display: flex;
    align-items: center;
    gap: 4px;
    transition: opacity 0.2s ease;
  `,
  confidenceBadge: css`
    display: inline-block;
    background: rgba(216, 162, 92, 0.1);
    color: var(--areqa-memory-accent);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    border: 1px solid rgba(216, 162, 92, 0.2);
    margin-right: 8px;
  `,
  refreshBtn: css`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: transparent;
    border: 1px solid color-mix(in srgb, var(--foreground) 20%, transparent);
    border-radius: 6px;
    color: var(--foreground);
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s ease;
    &:hover {
      background: color-mix(in srgb, var(--foreground) 10%, transparent);
      color: var(--foreground);
    }
  `,
  suggestionTitle: css`
    color: var(--areqa-memory-accent);
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 8px;
  `,
  suggestionCard: css`
    background: var(--card);
    border: 1px solid color-mix(in srgb, var(--foreground) 6%, transparent);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
  `,
}));
