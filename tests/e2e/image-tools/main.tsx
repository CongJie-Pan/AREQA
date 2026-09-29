import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { ChatInput } from '@/components/ChatInput';
import { MessageItem } from '@/components/MessageList/MessageItem';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { sendMessage, cancelCurrentStream, startNewConversation, regenerateMessage, initializeChatService, switchConversation } from '@/services/chat';
import { generateConversationImage, cancelConversationImage } from '@/services/generatedImages';
import { db } from '@/database/db';

localStorage.setItem('sb-e2e-auth-token', JSON.stringify({ user: { id: 'e2e-user' }, access_token: 'e2e-test-token', expires_at: 4102444800 }));

function Harness() {
  const [ready, setReady] = useState(false);
  const messages = useChatStore((state) => state.messages);
  const streaming = useChatStore((state) => state.isStreaming);
  const conversation = useConversationStore((state) => state.activeConversationId);
  const imageRequests = useChatStore((state) => state.imageGenerationRequests);
  const generatingImage = Object.values(imageRequests).some((request) => request.conversationId === conversation);
  useEffect(() => {
    Object.assign(window, { imageTest: { snapshot: () => db.messages.toArray(), conversations: () => db.conversations.toArray(), displayMessages: () => useChatStore.getState().messages } });
    void (async () => {
      await initializeChatService('e2e-user');
      const previous = useConversationStore.getState().conversations[0];
      if (previous) await switchConversation(previous.id);
      setReady(true);
    })();
  }, []);
  return <main style={{ maxWidth: 900, margin: '20px auto' }}>
    <button onClick={() => startNewConversation()}>新增測試對話</button>
    <ChatInput disabled={!ready || streaming || generatingImage} isStreaming={streaming}
      isGeneratingImage={generatingImage}
      onStop={() => { if (!cancelConversationImage(conversation)) void cancelCurrentStream(); }}
      onSend={(content, files, options) => options?.createImage
        ? generateConversationImage(content, conversation || undefined, 'zh-TW', true, { attachments: files })
        : sendMessage(content, conversation || undefined, files)} />
    {messages.map((message) => <MessageItem key={message.id} message={message}
      isStreaming={streaming && message.id === useChatStore.getState().currentStreamingId}
      onRegenerate={regenerateMessage} />)}
  </main>;
}

createRoot(document.getElementById('root')!).render(<UserPreferencesProvider><Harness /></UserPreferencesProvider>);
