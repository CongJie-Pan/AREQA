import React, { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LongConversationReminder } from '@/components/ChatContainer/LongConversationReminder';

vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn() } }));

const defaults = {
  userId: 'account-a', conversationId: 'conversation-a', messageCount: 99,
  blocked: false, onNewConversation: vi.fn(),
};

async function dismiss() {
  fireEvent.click(await screen.findByRole('button', { name: 'Continue this chat' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
}

describe('Long conversation reminder', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('offers new chat at 100, 103 and 106 total messages; keeps chatting after dismissal', async () => {
    const view = render(<LongConversationReminder {...defaults} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    for (const threshold of [100, 103, 106]) {
      view.rerender(<LongConversationReminder {...defaults} messageCount={threshold} />);
      expect(await screen.findByRole('dialog')).toHaveTextContent(`${threshold} messages`);
      await dismiss();
      for (const count of [threshold, threshold + 1, threshold + 2]) {
        view.rerender(<LongConversationReminder {...defaults} messageCount={count} />);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      }
    }
    expect(defaults.onNewConversation).not.toHaveBeenCalled();
  });

  it('defers while busy and catches a threshold crossed by a user/assistant pair', async () => {
    const view = render(<LongConversationReminder {...defaults} messageCount={100} />);
    await dismiss();
    view.rerender(<LongConversationReminder {...defaults} messageCount={103} blocked />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} messageCount={104} />);
    expect(await screen.findByRole('dialog')).toHaveTextContent('104 messages');
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(defaults.onNewConversation).toHaveBeenCalledOnce();
  });

  it('does not replay a shown milestone after remount, edits, deletes or switching chats', async () => {
    const first = render(<StrictMode><LongConversationReminder {...defaults} messageCount={103} /></StrictMode>);
    await screen.findByRole('dialog');
    first.unmount();
    const view = render(<LongConversationReminder {...defaults} messageCount={103} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} messageCount={98} />);
    view.rerender(<LongConversationReminder {...defaults} messageCount={103} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} conversationId="conversation-b" messageCount={100} />);
    await screen.findByRole('dialog');
    view.rerender(<LongConversationReminder {...defaults} messageCount={103} />);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('isolates accounts and opens only once for an existing very long conversation', async () => {
    const view = render(<LongConversationReminder {...defaults} messageCount={140} />);
    expect(await screen.findByRole('dialog')).toHaveTextContent('140 messages');
    await dismiss();
    view.rerender(<LongConversationReminder {...defaults} messageCount={140} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} userId="account-b" messageCount={140} />);
    await screen.findByRole('dialog');
    await dismiss();
    view.rerender(<LongConversationReminder {...defaults} userId="account-b" messageCount={142} />);
    await screen.findByRole('dialog');
  });

  it('keeps working when browser storage is denied', async () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied'); });
    try {
      const view = render(<LongConversationReminder {...defaults} messageCount={100} />);
      await dismiss();
      view.rerender(<LongConversationReminder {...defaults} messageCount={101} />);
      view.rerender(<LongConversationReminder {...defaults} messageCount={100} />);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      view.rerender(<LongConversationReminder {...defaults} messageCount={103} />);
      await screen.findByRole('dialog');
    } finally {
      get.mockRestore();
      set.mockRestore();
    }
  });

  it('does not prompt before a conversation exists or while history is loading', async () => {
    const view = render(<LongConversationReminder {...defaults} messageCount={100} conversationId={null} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} messageCount={100} blocked />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<LongConversationReminder {...defaults} messageCount={100} />);
    await screen.findByRole('dialog');
  });
});
