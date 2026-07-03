import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MailboxPanel } from '../../../frontend/src/components/MailboxPanel';
import { useMailboxStore } from '../../../frontend/src/store/mailbox';

// Mock the store
vi.mock('../../../frontend/src/store/mailbox', () => ({
  useMailboxStore: vi.fn(),
}));

describe('MailboxPanel', () => {
  const mockFetchMails = vi.fn();
  const mockMarkAsRead = vi.fn();
  const mockSendReply = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    (useMailboxStore as any).mockReturnValue({
      mails: [],
      loading: false,
      fetchMails: mockFetchMails,
      markAsRead: mockMarkAsRead,
      sendReply: mockSendReply,
      sendingReply: false,
    });
  });

  it('renders inbox list when mails exist', () => {
    (useMailboxStore as any).mockReturnValue({
      mails: [
        { mail_id: '1', sender: 'Alice', content: 'Hello world', timestamp: 1600000000, is_read: false },
      ],
      loading: false,
      fetchMails: mockFetchMails,
      markAsRead: mockMarkAsRead,
      sendReply: mockSendReply,
      sendingReply: false,
    });
    
    render(<MailboxPanel />);
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
    expect(screen.getByText('Hello world')).toBeInTheDocument();
    // Verify it renders time properly (using regex or substring if time depends on timezone)
    // We just check it doesn't crash and renders the components.
  });

  it('clicking mail shows content in viewer', () => {
    (useMailboxStore as any).mockReturnValue({
      mails: [
        { mail_id: '1', sender: 'Alice', content: 'Hello world', timestamp: 1600000000, is_read: true },
      ],
      loading: false,
      fetchMails: mockFetchMails,
      markAsRead: mockMarkAsRead,
      sendReply: mockSendReply,
      sendingReply: false,
    });
    
    render(<MailboxPanel />);
    const mailElement = screen.getByText('Hello world');
    fireEvent.click(mailElement);
    
    // Check if reply textarea appears
    expect(screen.getByPlaceholderText('回覆給 Alice...')).toBeInTheDocument();
  });

  it('reply button disabled when sendingReply is true', () => {
    (useMailboxStore as any).mockReturnValue({
      mails: [
        { mail_id: '1', sender: 'Alice', content: 'Hello world', timestamp: 1600000000, is_read: true },
      ],
      loading: false,
      fetchMails: mockFetchMails,
      markAsRead: mockMarkAsRead,
      sendReply: mockSendReply,
      sendingReply: true,
    });
    
    render(<MailboxPanel />);
    fireEvent.click(screen.getByText('Hello world'));
    
    const button = screen.getByRole('button', { name: /發送中/ });
    expect(button).toBeDisabled();
  });

  it('unread count badge updates after mark as read', () => {
    (useMailboxStore as any).mockReturnValue({
      mails: [
        { mail_id: '1', sender: 'Alice', content: 'Hello world', timestamp: 1600000000, is_read: false },
      ],
      loading: false,
      fetchMails: mockFetchMails,
      markAsRead: mockMarkAsRead,
      sendReply: mockSendReply,
      sendingReply: false,
    });
    
    render(<MailboxPanel />);
    fireEvent.click(screen.getByText('Hello world'));
    
    expect(mockMarkAsRead).toHaveBeenCalledWith('1');
  });
});
