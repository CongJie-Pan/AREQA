import 'fake-indexeddb/auto';
import React from 'react';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { ChatInput } from '@/components/ChatInput';
import { MessageItem } from '@/components/MessageList/MessageItem';
import { generateConversationImage, regenerateConversationImage } from '@/services/generatedImages';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { db } from '@/database/db';
import { messageRepo } from '@/database/repositories/messageRepo';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';

const render: typeof rtlRender = (ui, options) => rtlRender(ui, { wrapper: UserPreferencesProvider, ...options });

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: vi.fn(() => 'user-a'),
}));
vi.mock('@/services/database', async () => ({
  databaseService: { message: (await import('@/database/repositories/messageRepo')).messageRepo },
}));
vi.mock('@/services/syncService', () => ({
  syncService: { pushMessage: vi.fn(async () => true), pushConversation: vi.fn(async () => true) },
}));

function ImageConversation() {
  const messages = useChatStore((state) => state.messages);
  return <>
    <ChatInput onSend={(content, attachments, options) => (
      options?.createImage
        ? generateConversationImage(content, 'conv-a', 'zh-TW', true, { attachments })
        : Promise.resolve({ completed: true })
    )} />
    {messages.map((message) => <MessageItem key={message.id} message={message} onRegenerate={regenerateConversationImage} />)}
  </>;
}

beforeEach(async () => {
  window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  vi.clearAllMocks();
  await db.open();
  await db.messages.clear();
  await db.conversations.clear();
  useChatStore.getState().clearMessages();
  useConversationStore.setState({ activeConversationId: 'conv-a' });
  vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({ block: {
    type: 'image_block', slotId: 'image-a', topic: '細胞', purpose: 'diagram',
    imageUrl: 'https://example.test/cell.png', sourceUrl: '', sourceDomain: '',
    caption: '細胞圖', provider: 'generated_image', safetyStatus: 'pass',
    matchConfidence: 1, transient: false,
  } })));
});

afterEach(async () => {
  await db.messages.clear();
  await db.messageSyncQueue.clear();
  await db.conversationSyncQueue.clear();
  await db.conversations.clear();
});

it('creates an image from the plus menu and restores it from persisted conversation history', async () => {
  const view = render(<ImageConversation />);
  fireEvent.click(screen.getByLabelText('新增'));
  fireEvent.click(await screen.findByText('Create Image'));
  fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '畫一張細胞圖' } });
  fireEvent.click(screen.getByLabelText('發送訊息'));

  await waitFor(() => expect(screen.getByAltText('細胞圖')).toHaveAttribute('src', 'https://example.test/cell.png'));
  expect(authenticatedFetch).toHaveBeenCalledWith('/api/images/generate', expect.objectContaining({ method: 'POST' }));
  const saved = await messageRepo.getByConversationId('conv-a', 'user-a');
  expect(saved).toHaveLength(2);
  expect(saved[1].answerBlocks?.[0]).toMatchObject({ imageUrl: 'https://example.test/cell.png' });

  view.unmount();
  useChatStore.getState().setMessages(saved);
  render(<ImageConversation />);
  expect(screen.getByAltText('細胞圖')).toHaveAttribute('src', 'https://example.test/cell.png');
}, 15_000);

it('uses an attachment brief and retains image regeneration after reopening history', async () => {
  vi.mocked(authenticatedFetch).mockImplementation(async (url) => new Response(JSON.stringify(
    url === '/api/images/reference' ? { reference_brief: 'Photosynthesis converts light into sugar.' } : { block: {
      type: 'image_block', slotId: 'image-a', topic: '植物', purpose: 'diagram',
      imageUrl: 'https://example.test/plant.png', sourceUrl: '', sourceDomain: '', caption: '植物解說圖',
      provider: 'generated_image', safetyStatus: 'pass', matchConfidence: 1, transient: false,
    } },
  )));
  const view = render(<ImageConversation />);
  fireEvent.click(screen.getByLabelText('新增'));
  fireEvent.click(await screen.findByText('Create Image'));
  fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [new File(['Light becomes sugar.'], 'source.txt', { type: 'text/plain' })] } });
  fireEvent.change(screen.getByLabelText('訊息輸入框'), { target: { value: '根據附件產生解說圖' } });
  fireEvent.click(screen.getByLabelText('發送訊息'));
  await waitFor(() => expect(screen.getByAltText('植物解說圖')).toBeInTheDocument());
  const saved = await messageRepo.getByConversationId('conv-a', 'user-a');
  expect(saved).toHaveLength(2);
  view.unmount();
  useChatStore.getState().setMessages(saved);
  render(<ImageConversation />);
  fireEvent.click(screen.getByRole('button', { name: '重新生成訊息' }));
  await waitFor(() => expect(authenticatedFetch).toHaveBeenCalledTimes(3));
  await waitFor(() => expect(screen.getByAltText('植物解說圖')).toBeInTheDocument());
  const retryBody = JSON.parse(vi.mocked(authenticatedFetch).mock.calls[2][1]?.body as string);
  expect(retryBody.reference_brief).toBe('Photosynthesis converts light into sugar.');
  expect(vi.mocked(authenticatedFetch).mock.calls.map((call) => call[0])).toEqual([
    '/api/images/reference', '/api/images/generate', '/api/images/generate',
  ]);
  expect(await messageRepo.getByConversationId('conv-a', 'user-a')).toHaveLength(2);
}, 15_000);
