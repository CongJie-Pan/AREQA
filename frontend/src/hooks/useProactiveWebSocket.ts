import { useEffect, useRef } from 'react';

export function useProactiveWebSocket(
  onAlert: (content: string, senderName?: string) => void,
  onNewMail?: (sender: string) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const retryDelayRef = useRef(1000); // Initial backoff 1 second
  
  const onAlertRef = useRef(onAlert);
  const onNewMailRef = useRef(onNewMail);

  useEffect(() => {
    onAlertRef.current = onAlert;
    onNewMailRef.current = onNewMail;
  }, [onAlert, onNewMail]);

  useEffect(() => {
    let timeoutId: NodeJS.Timeout;

    function getAuthToken(): string | null {
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key && key.includes('-auth-token')) {
            const item = localStorage.getItem(key);
            if (item) {
              const parsed = JSON.parse(item);
              if (parsed?.access_token) {
                return parsed.access_token;
              }
            }
          }
        }
      } catch (e) {}
      return null;
    }

    async function connect() {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
      const wsUrl = backendUrl.replace(/^http/, 'ws');
      
      try {
        // Fetch One-Time Ticket
        const token = getAuthToken();
        const headers: Record<string, string> = {
          'Content-Type': 'application/json'
        };
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }
        
        const response = await fetch(`${backendUrl}/api/v1/ws/ticket`, {
          method: 'POST',
          headers: headers
        });
        
        if (!response.ok) {
          throw new Error('Failed to fetch WS ticket');
        }
        
        const data = await response.json();
        const ticket = data.ticket;

        wsRef.current = new WebSocket(`${wsUrl}/api/v1/ws/notifications?ticket=${ticket}`);

        wsRef.current.onmessage = (e) => {
          const msgData = JSON.parse(e.data);
          if (msgData.has_alert && msgData.content) {
            onAlertRef.current(msgData.content, msgData.sender_name);
          } else if (msgData.has_new_mail && msgData.sender && onNewMailRef.current) {
            onNewMailRef.current(msgData.sender);
          }
        };
        
        // On success: reset backoff
        wsRef.current.onopen = () => { 
          retryDelayRef.current = 1000; 
        };
        
        // On disconnect: exponential backoff reconnect (max 30s)
        wsRef.current.onclose = () => {
          timeoutId = setTimeout(connect, retryDelayRef.current);
          retryDelayRef.current = Math.min(retryDelayRef.current * 2, 30000);
        };
      } catch (e) {
        console.error('WebSocket connection error:', e);
        timeoutId = setTimeout(connect, retryDelayRef.current);
        retryDelayRef.current = Math.min(retryDelayRef.current * 2, 30000);
      }
    }

    connect();

    return () => {
      clearTimeout(timeoutId);
      if (wsRef.current) {
        // Prevent onclose from triggering reconnect loop when unmounting
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, []);
}
