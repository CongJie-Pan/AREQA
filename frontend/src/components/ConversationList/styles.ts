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

const titleMarquee = keyframes`
  0%,
  12% {
    transform: translateX(0);
  }
  88%,
  100% {
    transform: translateX(calc(-100% + var(--areqa-title-marquee-width, 100%)));
  }
`;

export const useStyles = createStyles(({ css }) => ({
  container: css`
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: #20201f;

    html[data-interface-theme='light'] & {
      background: #f8f8f6;
    }
    color: var(--foreground);

    button:focus-visible {
      outline: 2px solid var(--areqa-citation-border);
      outline-offset: -2px;
    }
  `,

  header: css`
    padding: 2px 8px 14px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  `,

  logoContainer: css`
    min-height: 45px;
    padding: 4px 12px 6px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  `,

  logoWrapper: css`
    display: flex;
    align-items: center;
    justify-content: flex-start;
    min-width: 0;
    min-height: 34px;
    padding: 0 4px;
    border: 0;
    border-radius: 7px;
    background: transparent;
    cursor: pointer;

    &:hover { background: var(--areqa-account-hover); }
  `,

  logoContainerExternalToggle: css`
    padding-inline-start: calc(max(8px, env(safe-area-inset-left)) + 38px);
    padding-top: max(4px, env(safe-area-inset-top));
  `,

  logo: css`
    width: 100px;
    height: auto;
    max-width: 100%;
    max-height: 30px;
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

  newButton: css`
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    min-height: 34px;
    padding: 5px 9px;
    background: color-mix(in srgb, var(--foreground) 13%, transparent);
    border: 0;
    border-radius: 8px;
    color: inherit;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;

    &:hover { background: color-mix(in srgb, var(--foreground) 19%, transparent); }
  `,

  searchButton: css`
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    min-height: 34px;
    padding: 5px 9px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: inherit;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;

    &:hover { background: var(--areqa-account-hover); }
  `,

  searchResults: css`
    display: grid;
    gap: 2px;
    max-height: min(50vh, 360px);
    overflow: auto;
    margin-top: 8px;
  `,

  searchResult: css`
    border: 0;
    border-radius: 7px;
    padding: 8px 10px;
    background: transparent;
    color: inherit;
    text-align: start;
    overflow-wrap: anywhere;
    cursor: pointer;

    &:hover, &:focus-visible { background: var(--areqa-account-hover); }
  `,

  list: css`
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 2px 8px 8px;
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

  group: css`
    flex: none;
  `,

  groupTitle: css`
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    min-height: 34px;
    padding: 5px 9px;
    border: 0;
    border-radius: 7px;
    background: transparent;
    color: var(--muted-foreground);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;

    &:hover { background: var(--areqa-account-hover); }
    &[aria-expanded='true'] svg { transform: rotate(90deg); }
  `,

  item: css`
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 2px 9px;
    min-height: 34px;
    border-radius: 7px;
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
    background: color-mix(in srgb, var(--foreground) 13%, transparent);

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
    --areqa-title-marquee-width: 100%;
    display: block;
    max-width: 100%;
    font-size: 14px;
    color: var(--foreground);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: color 0.2s;

    > span {
      display: inline-block;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      vertical-align: top;
      white-space: nowrap;
    }

    &[data-overflow='true']:hover,
    .areqa-conversation-item:hover &[data-overflow='true'] {
      text-overflow: clip;
    }

    &[data-overflow='true']:hover > span,
    .areqa-conversation-item:hover &[data-overflow='true'] > span {
      max-width: none;
      overflow: visible;
      text-overflow: clip;
      animation: ${titleMarquee} 5.5s linear infinite alternate;
      will-change: transform;
    }

    @media (prefers-reduced-motion: reduce) {
      &[data-overflow='true']:hover > span,
      .areqa-conversation-item:hover &[data-overflow='true'] > span {
        animation: none;
      }
    }
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

  accountFooter: css`
    flex: none;
    border-top: 1px solid var(--areqa-subtle-border);
  `,

  menuLabel: css`
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 22px;

    > svg {
      display: block;
      flex: 0 0 14px;
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

    &:focus-visible { opacity: 1; }

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

  emptyText: css`
    padding: 6px 9px;
    color: var(--muted-foreground);
    font-size: 13px;
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
