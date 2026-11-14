import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MessageItem } from '@/components/MessageList/MessageItem';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import type { DisplayMessage } from '@/store/chat';

const response: DisplayMessage = {
  id: 'answered-message',
  userId: 'branch-user',
  conversationId: 'branch-source',
  role: 'assistant',
  content: '一般對話的回覆',
  createdAt: new Date(2026, 10, 14),
};

function renderReply(onBranch: (messageId: string) => void, isStreaming: boolean, withActions = false) {
  return render(
    <UserPreferencesProvider initialPreferences={{ theme: 'system', language: 'zh-TW' }}>
      <App>
        <MessageItem
          message={response}
          isStreaming={isStreaming}
          onBranch={onBranch}
          {...(withActions ? { onFeedback: vi.fn(), onRegenerate: vi.fn(), onAddNote: vi.fn(),
            onEdit: vi.fn(), onDeleteLatestTurn: vi.fn() } : {})}
        />
      </App>
    </UserPreferencesProvider>,
  );
}

describe('MessageItem branch menu', () => {
  it('uses a fork icon and forwards the selected reply id', async () => {
    const onBranch = vi.fn();
    renderReply(onBranch, false);

    fireEvent.click(screen.getByRole('button', { name: '更多回覆操作' }));
    const item = await screen.findByRole('menuitem', { name: '建立新對話分支' });
    expect(item.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(onBranch).not.toHaveBeenCalled();
    fireEvent.click(item);
    expect(onBranch).toHaveBeenCalledExactlyOnceWith('answered-message');
  });

  it('orders the visible reply buttons and keeps secondary actions in the menu', async () => {
    const { container } = renderReply(vi.fn(), false, true);
    const toolbar = screen.getByRole('button', { name: '更多回覆操作' }).parentElement!;
    expect(Array.from(toolbar.querySelectorAll('button'), button => button.getAttribute('aria-label'))).toEqual([
      '這則回覆有幫助', '這則回覆沒有幫助', '重新生成訊息', '複製訊息', '加入筆記', '更多回覆操作',
    ]);
    expect(container.querySelector('button[aria-label="加入筆記"] svg')).toHaveClass('lucide-bookmark');

    fireEvent.click(screen.getByRole('button', { name: '更多回覆操作' }));
    expect((await screen.findAllByRole('menuitem')).map(item => item.textContent)).toEqual([
      '建立新對話分支', '朗讀回覆', '編輯訊息', '刪除對話',
    ]);
  });

  it('does not expose branching for a reply that is still streaming', () => {
    renderReply(vi.fn(), true);
    expect(screen.queryByRole('button', { name: '更多回覆操作' })).not.toBeInTheDocument();
  });
});
