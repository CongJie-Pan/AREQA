import { create } from 'zustand';

export interface Mail {
  mail_id: string;
  sender: string;
  subject?: string;
  recipient: string;
  content: string;
  timestamp: number;
  is_read: boolean;
  conversation_id?: string;
}

interface MailboxState {
  mails: Mail[];
  unreadCount: number;
  loading: boolean;
  sendingReply: boolean;
  error: string | null;
  fetchMails: () => Promise<void>;
  sendReply: (content: string, recipient: string) => Promise<boolean>;
  markAsRead: (mailId: string) => Promise<void>;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export const useMailboxStore = create<MailboxState>((set, get) => ({
  mails: [],
  unreadCount: 0,
  loading: false,
  sendingReply: false,
  error: null,

  fetchMails: async () => {
    set({ loading: true, error: null });
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/mailbox`);
      if (!response.ok) throw new Error('Failed to fetch mails');
      const data = await response.json();
      
      // Sort by timestamp descending
      const sortedMails = data.mails.sort((a: Mail, b: Mail) => b.timestamp - a.timestamp);
      
      set({ 
        mails: sortedMails, 
        unreadCount: data.unread_count,
        loading: false 
      });
    } catch (err: unknown) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  sendReply: async (content: string, recipient: string) => {
    set({ sendingReply: true, error: null });
    
    // Optimistic Update
    const tempId = `temp-${Date.now()}`;
    const tempMail: Mail = {
      mail_id: tempId,
      sender: "User",
      recipient,
      content,
      timestamp: Date.now() / 1000,
      is_read: true, // Our own mail is always read
    };
    
    const previousMails = get().mails;
    set({ mails: [tempMail, ...previousMails], sendingReply: false });

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/mailbox/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, recipient }),
      });
      
      if (!response.ok) throw new Error('Failed to send reply');
      const data = await response.json();
      
      // Update with real ID
      set((state) => ({
        mails: state.mails.map(m => m.mail_id === tempId ? { ...m, mail_id: data.mail_id } : m)
      }));
      return true;
    } catch (err: unknown) {
      // Revert optimistic update on failure
      set({ mails: previousMails, error: (err as Error).message });
      return false;
    }
  },

  markAsRead: async (mailId: string) => {
    // Optimistic Update
    const previousMails = get().mails;
    const previousUnread = get().unreadCount;
    
    set((state) => ({
      mails: state.mails.map(m => m.mail_id === mailId ? { ...m, is_read: true } : m),
      unreadCount: Math.max(0, state.unreadCount - 1)
    }));

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/mailbox/read/${mailId}`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to mark as read');
    } catch (err: unknown) {
      // Revert if failed
      set({ mails: previousMails, unreadCount: previousUnread, error: (err as Error).message });
    }
  }
}));
