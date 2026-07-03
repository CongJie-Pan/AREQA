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

    function connect() {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
      const wsUrl = backendUrl.replace(/^http/, 'ws');
      wsRef.current = new WebSocket(`${wsUrl}/api/v1/ws/notifications?user_id=default_user`);

      wsRef.current.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.has_alert && data.content) {
          onAlertRef.current(data.content, data.sender_name);
        } else if (data.has_new_mail && data.sender && onNewMailRef.current) {
          onNewMailRef.current(data.sender);
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
