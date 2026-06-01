import { createStyles } from 'antd-style';

export const useStyles = createStyles(({ css }) => ({
  toolbar: css`
    position: fixed;
    z-index: 1000;
    display: flex;
    align-items: center;
    background: #434343;
    border-radius: 8px;
    padding: 2px 6px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
    gap: 4px;
    pointer-events: auto;
    border: 1px solid #595959;
    animation: fadeIn 0.15s ease-out;

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `,
  button: css`
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 0 10px;
    height: 32px;
    border: none;
    background: transparent;
    color: #e8e8e8;
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.2s;
    font-size: 13px;
    font-weight: 500;

    &:hover {
      background: #595959;
      color: #ffffff;
    }

    &:active {
      background: #757575;
    }

    svg {
      flex-shrink: 0;
    }
  `,
  divider: css`
    width: 1px;
    height: 18px;
    background: #595959;
    margin: 0 2px;
  `,
  label: css`
    white-space: nowrap;
  `,
}));
