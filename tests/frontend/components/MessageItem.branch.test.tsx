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

function renderReply(onBranch: (messageId: string) => void, isStreaming: boolean) {
  return render(
    <UserPreferencesProvider initialPreferences={{ theme: 'system', language: 'zh-TW' }}>
      <App>
        <MessageItem message={response} isStreaming={isStreaming} onBranch={onBranch} />
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

  it('does not expose branching for a reply that is still streaming', () => {
    renderReply(vi.fn(), true);
    expect(screen.queryByRole('button', { name: '更多回覆操作' })).not.toBeInTheDocument();
  });
});
