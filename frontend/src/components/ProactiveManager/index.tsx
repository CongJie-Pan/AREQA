import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useProactiveWebSocket } from '@/hooks/useProactiveWebSocket';
import { App, Button, Input } from 'antd';
import { BulbOutlined, CheckOutlined, CloseOutlined, SendOutlined } from '@ant-design/icons';
import { useConversationStore } from '@/store/conversation';

const AutoRejectButton = ({ onReject }: { onReject: () => void }) => {
  return (
    <Button 
      onClick={onReject} 
      icon={<CloseOutlined />} 
    >
      不需要協助
    </Button>
  );
};

const QuickReplyPanel = ({ content, onReject, onAccept, onSend }: { content: string, onReject: () => void, onAccept: () => void, onSend: (text: string) => void }) => {
  const [text, setText] = useState('');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '8px' }}>
      <div style={{ fontSize: '14px', lineHeight: '1.5' }}>{content}</div>
      <Input
        placeholder="或直接輸入您的想法..."
        value={text}
        onChange={e => setText(e.target.value)}
        onPressEnter={() => text.trim() && onSend(text)}
      />
      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '4px' }}>
        <AutoRejectButton onReject={onReject} />
        {!text.trim() ? (
          <Button type="primary" icon={<CheckOutlined />} onClick={onAccept}>
            請繼續
          </Button>
        ) : (
          <Button type="primary" icon={<SendOutlined />} onClick={() => onSend(text)}>
            傳送回覆
          </Button>
        )}
      </div>
    </div>
  );
};

export const ProactiveManager: React.FC = () => {
  const { notification, message } = App.useApp();
  const lastScrollTime = useRef(0);
  const lastScrollY = useRef(-1);

  // 1. Polling proactive-check
  const handleAlert = useCallback((content: string, senderName?: string) => {
    const key = `proactive-${Date.now()}`;

    const waitForStreamAndSend = async (textToUser: string) => {
      notification.destroy(key);
      const { useChatStore } = await import('@/store/chat');
      
      let isPending = false;
      let hideMessage = () => {};
      
      // Wait while system is streaming
      while (useChatStore.getState().isStreaming) {
        if (!isPending) {
          isPending = true;
          hideMessage = message.loading('等待系統回覆完畢後，將自動為您送出...', 0);
        }
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      
      if (isPending) {
        hideMessage();
        message.success('已送出！');
      }

      const { activeConversationId } = useConversationStore.getState();
      const { sendMessage, insertAssistantMessage } = await import('@/services/chat');
      await insertAssistantMessage(content, activeConversationId || undefined);
      sendMessage(textToUser, activeConversationId || undefined);
    };

    const handleAccept = async () => {
      await waitForStreamAndSend('好，請繼續幫我梳理一下。');
    };

    const handleSend = async (text: string) => {
      await waitForStreamAndSend(text);
    };

    const handleReject = async () => {
      notification.destroy(key);
      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
        await fetch(`${backendUrl}/api/v1/log_action`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action_type: 'compeer_rejected', timestamp: Date.now(), context: {} }),
        });
      } catch {
        // Silently fail — rejection should always close the notification regardless
      }
    };

    notification.info({
      key,
      title: senderName || 'AREQA',
      message: senderName || 'AREQA',
      description: (
        <QuickReplyPanel 
          content={content} 
          onReject={handleReject} 
          onAccept={handleAccept} 
          onSend={handleSend} 
        />
      ),
      icon: <BulbOutlined style={{ color: '#d8a25c' }} />,
      placement: 'top',
      duration: 0, // Auto close handled by AutoRejectButton
      btn: <span />, // Hide default btn section because we rendered buttons in QuickReplyPanel
    });
  }, [notification, message]);

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
