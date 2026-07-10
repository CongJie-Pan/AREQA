import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useMailboxStore } from '../../../frontend/src/store/mailbox';

// Mock fetch globally
const fetchMock = vi.fn();
global.fetch = fetchMock;

describe('mailboxStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMailboxStore.setState({
      mails: [],
      unreadCount: 0,
      loading: false,
      sendingReply: false,
      error: null
    });
  });

  describe('fetchMails', () => {
    it('fetches mails and updates store', async () => {
      // Arrange
      const EXPECTED_MAILS = [
        { mail_id: '1', sender: 'A', recipient: 'B', content: 'C', timestamp: 1000, is_read: false }
      ];
      fetchMock.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ mails: EXPECTED_MAILS, unread_count: 1 })
      });

      // Act
      await useMailboxStore.getState().fetchMails();

      // Assert
      const state = useMailboxStore.getState();
      expect(state.mails).toEqual(EXPECTED_MAILS);
      expect(state.unreadCount).toBe(1);
      expect(state.loading).toBe(false);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/mailbox'),
        expect.objectContaining({ headers: expect.any(Object) })
      );
    });
  });

  describe('sendReply', () => {
    it('sendReply sets sendingReply to true then false', async () => {
      // Arrange
      const EXPECTED_CONTENT = 'reply content';
      const EXPECTED_RECIPIENT = 'A';
      
      fetchMock.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ mail_id: 'real-1' })
      });

      let observedTrue = false;
      const unsubscribe = useMailboxStore.subscribe((state) => {
        if (state.sendingReply) {
          observedTrue = true;
        }
      });

      // Act
      await useMailboxStore.getState().sendReply(EXPECTED_CONTENT, EXPECTED_RECIPIENT);

      // Assert
      expect(observedTrue).toBe(true);
      expect(useMailboxStore.getState().sendingReply).toBe(false);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/mailbox/send'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ content: EXPECTED_CONTENT, recipient: EXPECTED_RECIPIENT })
        })
      );
      
      unsubscribe();
    });

    it('keeps sendingReply true while the reply request is pending', async () => {
      let resolveFetch: (value: { ok: boolean; json: () => Promise<{ mail_id: string }> }) => void;
      fetchMock.mockReturnValue(
        new Promise((resolve) => {
          resolveFetch = resolve;
        })
      );

      const sendPromise = useMailboxStore.getState().sendReply('pending reply', 'AREQA');

      expect(useMailboxStore.getState().sendingReply).toBe(true);
      expect(useMailboxStore.getState().mails).toHaveLength(1);

      resolveFetch!({
        ok: true,
        json: () => Promise.resolve({ mail_id: 'real-pending-1' }),
      });
      await sendPromise;

      expect(useMailboxStore.getState().sendingReply).toBe(false);
      expect(useMailboxStore.getState().mails[0].mail_id).toBe('real-pending-1');
    });
  });

  describe('markAsRead', () => {
    it('markAsRead updates local state', async () => {
      // Arrange
      const INITIAL_MAIL = { mail_id: '1', sender: 'A', recipient: 'B', content: 'C', timestamp: 1000, is_read: false };
      useMailboxStore.setState({
        mails: [INITIAL_MAIL],
        unreadCount: 1
      });
      
      fetchMock.mockResolvedValue({ ok: true });

      // Act
      // The update is optimistic so it should be visible before fetch completes, but we await anyway to avoid unhandled promises
      await useMailboxStore.getState().markAsRead('1');

      // Assert
      const state = useMailboxStore.getState();
      expect(state.mails[0].is_read).toBe(true);
      expect(state.unreadCount).toBe(0);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/mailbox/read/1'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });
});
