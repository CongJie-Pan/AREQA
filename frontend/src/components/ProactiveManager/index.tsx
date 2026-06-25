import React, { useEffect, useRef, useState } from 'react';
import { App, Button } from 'antd';
import { BulbOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useConversationStore } from '@/store/conversation';

const AutoRejectButton = ({ onReject, durationMs = 20000 }: { onReject: () => void, durationMs?: number }) => {
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    const startTime = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, 100 - (elapsed / durationMs) * 100);
      setProgress(remaining);
      if (elapsed >= durationMs) {
        clearInterval(interval);
        onReject();
      }
    }, 50);
    return () => clearInterval(interval);
  }, [onReject, durationMs]);

  return (
    <Button 
      onClick={onReject} 
      icon={<CloseOutlined />} 
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      <div 
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          height: '3px',
          backgroundColor: '#ff4d4f',
          width: `${progress}%`,
          transition: 'width 50ms linear'
        }}
      />
      不需要
    </Button>
  );
};

export function ProactiveManager() {
  const { notification } = App.useApp();
  const lastScrollTime = useRef(0);
  const lastScrollY = useRef(-1);

  // 1. Polling proactive-check
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
        const res = await fetch(`${backendUrl}/api/v1/proactive-check?user_id=default_user`);
        const data = await res.json();
        if (data.has_alert && data.content) {
          const key = `proactive-${Date.now()}`;

          const handleAccept = async () => {
            notification.destroy(key); // Close the notification
            const { activeConversationId } = useConversationStore.getState();
            if (activeConversationId) {
              // Also automatically send a user message asking for help
              const { sendMessage } = await import('@/services/chat');
              sendMessage('好，我需要協助，請根據我們目前的討論幫我梳理一下。', activeConversationId);
            }
          };

          const handleReject = () => {
            notification.destroy(key);
          };

          notification.info({
            key,
            title: 'AREQA',
            message: 'AREQA',
            description: data.content,
            icon: <BulbOutlined style={{ color: '#d8a25c' }} />,
            placement: 'top',
            duration: 0, // Auto close handled by AutoRejectButton
            btn: (
              <div style={{ display: 'flex', gap: '8px' }}>
                <AutoRejectButton onReject={handleReject} durationMs={20000} />
                <Button type="primary" icon={<CheckOutlined />} onClick={handleAccept}>
                  需要協助
                </Button>
              </div>
            ),
          });
        }
      } catch (err) {
        console.error('Proactive check failed:', err);
      }
    }, 30000); // 30 seconds

    return () => clearInterval(timer);
  }, [notification]);

  // 2. Action Telemetry (Scroll, MouseMove)
  useEffect(() => {
    const logAction = async (action: string, context: Record<string, unknown>) => {
      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
        await fetch(`${backendUrl}/api/v1/log_action`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
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
