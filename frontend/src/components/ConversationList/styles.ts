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

const titleSkeletonShimmer = keyframes`
  from {
    background-position: 160% 0;
  }
  to {
    background-position: -60% 0;
  }
`;

export const useStyles = createStyles(({ css }) => ({
  container: css`
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--areqa-sidebar-background);
    color: var(--foreground);
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
    width: min(164px, 100%);
    height: auto;
    max-height: 40px;
    object-fit: contain;
    flex-shrink: 0;
  `,

  logoDark: css`
    display: block;

    html[data-interface-theme='light'] & {
      display: none;
    }
  `,

  logoLight: css`
    display: none;

    html[data-interface-theme='light'] & {
      display: block;
    }
  `,

  toggleButton: css`
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    background: transparent;
    border: none;
    color: var(--muted-foreground);
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.2s;
    flex-shrink: 0;

    &:hover {
      background: var(--areqa-account-hover);
      color: var(--foreground);
    }
  `,

  title: css`
    font-size: 14px;
    font-weight: 600;
    color: var(--muted-foreground);
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
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: var(--foreground);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: var(--areqa-account-hover);
      border-color: transparent;
    }

    svg {
      color: #d8a25c;
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
    color: var(--muted-foreground);
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
      background: var(--areqa-account-hover);
      
      .conversation-menu-btn {
        opacity: 1;
      }
    }
  `,

  itemActive: css`
    background: color-mix(in srgb, #6f2f45 26%, transparent) !important;
    
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 20%;
      height: 60%;
      width: 3px;
      background: #6f2f45;
      border-radius: 0 2px 2px 0;
    }

    .conv-title {
      color: var(--foreground);
      font-weight: 500;
    }
  `,

  itemIcon: css`
    color: var(--muted-foreground);
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
    color: var(--foreground);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: color 0.2s;
  `,

  cursor: css`
    display: inline-block;
    width: 2px;
    height: 14px;
    background: #d8a25c;
    margin-left: 2px;
    vertical-align: middle;
    animation: ${cursorBlink} 1s step-end infinite;
  `,

  titleSkeleton: css`
    display: block;
    width: min(72%, 132px);
    height: 16px;
    border-radius: 4px;
    background:
      linear-gradient(
        100deg,
        transparent 0%,
        rgba(255, 255, 255, 0.18) 42%,
        rgba(255, 255, 255, 0.42) 50%,
        rgba(255, 255, 255, 0.18) 58%,
        transparent 100%
      ),
      var(--areqa-account-hover);
    background-size: 220% 100%, 100% 100%;
    animation: ${titleSkeletonShimmer} 1.2s ease-in-out infinite;

    html[data-interface-theme='light'] & {
      background:
        linear-gradient(
          100deg,
          transparent 0%,
          rgba(17, 24, 39, 0.06) 42%,
          rgba(17, 24, 39, 0.16) 50%,
          rgba(17, 24, 39, 0.06) 58%,
          transparent 100%
        ),
        var(--areqa-account-hover);
      background-size: 220% 100%, 100% 100%;
    }

    @media (prefers-reduced-motion: reduce) {
      animation: none;
    }
  `,

  deleteBtn: css`
    opacity: 0;
    padding: 4px;
    border-radius: 4px;
    color: var(--muted-foreground);
    transition: all 0.2s;
    flex-shrink: 0;

    &:hover {
      color: #ff4d4f;
      background: var(--areqa-danger-hover);
    }
  `,

  menuBtn: css`
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    flex-shrink: 0;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--muted-foreground);
    cursor: pointer;
    opacity: 0;
    transition: all 0.2s;

    &:hover {
      color: var(--foreground);
      background: var(--areqa-account-hover);
    }

    @media (max-width: 768px) {
      display: none;
    }
  `,

  pinnedIcon: css`
    color: #d8a25c;
    flex-shrink: 0;
    opacity: 0.86;
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
    color: var(--muted-foreground);
  `,

  emptyText: css`
    font-size: 13px;
    color: var(--muted-foreground);
    line-height: 1.6;
  `,

  divider: css`
    height: 1px;
    background: var(--border);
    margin: 4px 0;
  `,

  gumButton: css`
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: transparent;
    border-width: 1px;
    border-style: solid;
    border-color: var(--border);
    border-radius: 8px;
    color: var(--muted-foreground);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    
    &:hover {
      background: rgba(216, 162, 92, 0.1);
      border-color: rgba(216, 162, 92, 0.3);
      color: #d8a25c;
    }
    
    svg {
      color: #d8a25c;
    }
  `,
}));
