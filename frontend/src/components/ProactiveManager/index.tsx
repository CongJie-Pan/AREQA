import React, { useEffect, useRef } from 'react';
import { App } from 'antd';
import { BulbOutlined } from '@ant-design/icons';
import { sendMessage } from '@/services/chat';
import { useConversationStore } from '@/store/conversation';

export function ProactiveManager() {
  const { notification } = App.useApp();
  const lastScrollTime = useRef(0);

  // 1. Polling proactive-check
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const res = await fetch('http://localhost:8000/api/v1/proactive-check?user_id=default_user');
        const data = await res.json();
        if (data.has_alert && data.content) {
          notification.info({
            message: '小紅關心您',
            description: data.content,
            icon: <BulbOutlined style={{ color: '#d8a25c' }} />,
            duration: null, // Don't auto close
            onClick: () => {
              const activeConversationId = useConversationStore.getState().activeConversationId;
              sendMessage(data.content, activeConversationId || undefined);
            },
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
    const logAction = async (action: string, context: Record<string, any>) => {
      try {
        await fetch('http://localhost:8000/api/v1/log_action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action_type: action,
            timestamp: Date.now(),
            context
          }),
        });
      } catch (err) {}
    };

    const handleScroll = () => {
      const now = Date.now();
      if (now - lastScrollTime.current > 5000) { // Throttle scroll logs to every 5s
        lastScrollTime.current = now;
        logAction('scroll', { scrollY: window.scrollY });
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    
    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  return null;
}
