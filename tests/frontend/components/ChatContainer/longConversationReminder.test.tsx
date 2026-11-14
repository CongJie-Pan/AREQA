import React, { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LongConversationReminder } from '@/components/ChatContainer/LongConversationReminder';

vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn() } }));

const defaults = {
  userId: 'account-a', conversationId: 'conversation-a', replyCount: 99,
  blocked: false, onNewConversation: vi.fn(),
};

async function dismiss() {
  fireEvent.click(await screen.findByRole('button', { name: 'Continue this chat' }));
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
}

describe('Long conversation reminder', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('offers new chat at 100, 105 and 110 assistant replies; keeps chatting after dismissal', async () => {
    const view = render(<LongConversationReminder {...defaults} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    for (const threshold of [100, 105, 110]) {
      view.rerender(<LongConversationReminder {...defaults} replyCount={threshold} />);
      expect(await screen.findByRole('status')).toHaveTextContent(`${threshold} AI replies`);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(document.querySelector('[aria-modal="true"]')).toBeNull();
      await dismiss();
      for (const count of [threshold, threshold + 1, threshold + 2, threshold + 3, threshold + 4]) {
        view.rerender(<LongConversationReminder {...defaults} replyCount={count} />);
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
      }
    }
    expect(defaults.onNewConversation).not.toHaveBeenCalled();
  });

  it('offers branching via an earlier reply only when branching is available', async () => {
    const view = render(<LongConversationReminder {...defaults} replyCount={100} canCreateBranch />);
    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('Use the ⋯ menu on an earlier reply to branch from that point');
    expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument();

    view.rerender(<LongConversationReminder {...defaults} replyCount={100} />);
    expect(notice).not.toHaveTextContent('to branch from that point');
    expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument();
  });

  it('defers while busy and catches a threshold crossed by a reply-count jump', async () => {
    const view = render(<LongConversationReminder {...defaults} replyCount={100} />);
    await dismiss();
    view.rerender(<LongConversationReminder {...defaults} replyCount={105} blocked />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} replyCount={106} />);
    expect(await screen.findByRole('status')).toHaveTextContent('106 AI replies');
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(defaults.onNewConversation).toHaveBeenCalledOnce();
  });

  it('does not replay a shown milestone after remount, edits, deletes or switching chats', async () => {
    const first = render(<StrictMode><LongConversationReminder {...defaults} replyCount={105} /></StrictMode>);
    await screen.findByRole('status');
    first.unmount();
    const view = render(<LongConversationReminder {...defaults} replyCount={105} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} replyCount={98} />);
    view.rerender(<LongConversationReminder {...defaults} replyCount={105} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} conversationId="conversation-b" replyCount={100} />);
    await screen.findByRole('status');
    view.rerender(<LongConversationReminder {...defaults} replyCount={105} />);
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
  });

  it('isolates accounts and opens only once for an existing very long conversation', async () => {
    const view = render(<LongConversationReminder {...defaults} replyCount={140} />);
    expect(await screen.findByRole('status')).toHaveTextContent('140 AI replies');
    await dismiss();
    view.rerender(<LongConversationReminder {...defaults} replyCount={140} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} userId="account-b" replyCount={140} />);
    await screen.findByRole('status');
    await dismiss();
    view.rerender(<LongConversationReminder {...defaults} userId="account-b" replyCount={145} />);
    await screen.findByRole('status');
  });

  it('keeps working when browser storage is denied', async () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied'); });
    try {
      const view = render(<LongConversationReminder {...defaults} replyCount={100} />);
      await dismiss();
      view.rerender(<LongConversationReminder {...defaults} replyCount={101} />);
      view.rerender(<LongConversationReminder {...defaults} replyCount={100} />);
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      view.rerender(<LongConversationReminder {...defaults} replyCount={105} />);
      await screen.findByRole('status');
    } finally {
      get.mockRestore();
      set.mockRestore();
    }
  });

  it('leaves typing and focus available while the inline reminder is visible', async () => {
    render(<><input aria-label="Message" /><LongConversationReminder {...defaults} replyCount={100} /></>);
    const input = screen.getByRole('textbox', { name: 'Message' });
    input.focus();
    await screen.findByRole('status');
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: 'Continue the conversation' } });
    expect(input).toHaveValue('Continue the conversation');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not reuse the previous total-message milestone', async () => {
    localStorage.setItem('areqa:long-conversation-reminder:v1:account-a:conversation-a', '400');
    render(<LongConversationReminder {...defaults} replyCount={100} />);
    await screen.findByRole('status');
  });

  it('does not prompt before a conversation exists or while history is loading', async () => {
    const view = render(<LongConversationReminder {...defaults} replyCount={100} conversationId={null} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} replyCount={100} blocked />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} replyCount={100} />);
    await screen.findByRole('status');
  });
});
