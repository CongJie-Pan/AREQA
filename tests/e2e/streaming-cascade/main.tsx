import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from 'antd';
import { MessageItem } from '@/components/MessageList/MessageItem';
import type { DisplayMessage } from '@/store/chat';
import 'streamdown/styles.css';

const initial: DisplayMessage = {
  id: 'cascade-replay', userId: 'test', conversationId: 'test', role: 'assistant', content: '', createdAt: new Date(),
};

declare global {
  interface Window {
    cascadeReplay: (content: string, receiving: boolean, slots?: DisplayMessage['streamImageSlots']) => void;
  }
}

function Replay() {
  const [frame, setFrame] = useState({ message: initial, receiving: false });
  useEffect(() => {
    window.cascadeReplay = (content, receiving, streamImageSlots) => setFrame({
      message: { ...initial, content, streamImageSlots }, receiving,
    });
  }, []);
  return <App><main style={{ width: 720, maxWidth: '90vw', margin: '30px auto' }}>
    <MessageItem message={frame.message} isStreaming={frame.receiving} />
  </main></App>;
}

createRoot(document.getElementById('root')!).render(<Replay />);
