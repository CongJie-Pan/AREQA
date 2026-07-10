import React, { useEffect, useRef, useCallback } from 'react';
import { useProactiveWebSocket } from '@/hooks/useProactiveWebSocket';
import { getAuthToken } from '@/database/db';

export const ProactiveManager: React.FC = () => {
  const lastScrollTime = useRef(0);
  const lastScrollY = useRef(-1);

  const handleAlert = useCallback(() => {
    // ComPeer care now arrives asynchronously through mailbox letters.
    // Legacy alert payloads are intentionally ignored to avoid interrupting the chat.
  }, []);

  // 以 hook 取代 setInterval
  const handleNewMail = useCallback(() => {
    import('@/store/mailbox').then(({ useMailboxStore }) => {
      useMailboxStore.getState().fetchMails();
    });
  }, []);

  useProactiveWebSocket(handleAlert, handleNewMail);

  // 2. Action Telemetry (Scroll, MouseMove)
  useEffect(() => {
    const logAction = async (action: string, context: Record<string, unknown>) => {
      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
        const token = getAuthToken();
        await fetch(`${backendUrl}/api/v1/log_action`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          },
          body: JSON.stringify({
            action_type: action,
            timestamp: Date.now(),
            context
          }),
        });
      } catch {
        // Ignored
      }
    };

    const handleScroll = (e: Event) => {
      const now = Date.now();
      const target = e.target as HTMLElement;
      // Get the actual scroll position from the scrolling element, fallback to window.scrollY
      const currentScrollY = target.scrollTop ?? window.scrollY;

      if (now - lastScrollTime.current > 5000) {
        // Initialize lastScrollY if it's the first time
        if (lastScrollY.current === -1) {
          lastScrollY.current = currentScrollY;
          return;
        }

        // Only count as a meaningful "scroll" if they moved more than 100 pixels
        if (Math.abs(currentScrollY - lastScrollY.current) > 100) {
          lastScrollTime.current = now;
          lastScrollY.current = currentScrollY;
          logAction('scroll', { scrollY: currentScrollY });
        }
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true, capture: true });
    
    return () => {
      window.removeEventListener('scroll', handleScroll, { capture: true });
    };
  }, []);

  return null;
}
