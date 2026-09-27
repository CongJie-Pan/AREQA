/** Shared text and voice image generation workflow. */

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import type { ImageBlock } from '@/database/schema';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { generateUUID } from '@/utils/id';
import { logger } from '@/utils/logger';

export interface GeneratedImageResult {
  completed: boolean;
  conversationId?: string;
  block?: ImageBlock;
}

/** Generate a single image while leaving the conversation free for new turns.
 *
 * Args:
 *   request: The user's explicit drawing request.
 *   conversationId: Existing conversation, if one has been selected.
 *   language: Label language for the generated visual.
 *   persistUserTurn: Whether the caller already recorded the voice transcript.
 *
 * Returns:
 *   A promise resolved after the image card has been updated and persisted.
 *
 * Side Effects:
 *   Creates chat messages, calls the authenticated image proxy, and stores the
 *   completed image metadata. The provider key never enters the browser.
 */
export async function generateConversationImage(
  request: string,
  conversationId: string | undefined,
  language: 'zh-TW' | 'zh-CN' | 'en',
  persistUserTurn = true,
): Promise<GeneratedImageResult> {
  const prompt = request.trim();
  if (prompt.length < 3 || prompt.length > 1800 || !getCurrentUserId()) {
    return { completed: false };
  }
  const conversations = useConversationStore.getState();
  let id = conversationId || conversations.activeConversationId || undefined;
  if (!id) {
    const conversation = await databaseService.conversation.create();
    id = conversation.id;
    useConversationStore.setState((state) => ({ conversations: [conversation, ...state.conversations] }));
    conversations.selectConversation(id);
  }
  if (persistUserTurn) {
    const userId = useChatStore.getState().addUserMessage(prompt, id);
    await databaseService.message.add(id, { id: userId, role: 'user', content: prompt });
  }
  const assistantId = useChatStore.getState().addAssistantMessage(id);
  const pendingBlock: ImageBlock = {
    type: 'image_block', slotId: generateUUID(), topic: prompt.slice(0, 180),
    purpose: 'diagram', imageUrl: '', sourceUrl: '', sourceDomain: '',
    caption: language === 'en' ? 'Creating image…' : '正在產生圖片…',
    provider: 'generated_image', status: 'pending', safetyStatus: 'pass',
    matchConfidence: 1,
  };
  useChatStore.getState().updateAssistantMessage(assistantId, {
    isStreaming: false, answerBlocks: [pendingBlock],
  });
  logger.info('image_generation_started', { conversationId: id, assistantId });
  try {
    const response = await authenticatedFetch('/api/images/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, conversation_id: id, interface_language: language }),
    });
    if (!response.ok) throw new Error(`Image generation failed (${response.status})`);
    const payload = await response.json() as { block?: ImageBlock };
    if (!payload.block || payload.block.type !== 'image_block' || !payload.block.imageUrl) {
      throw new Error('Image generation returned no image');
    }
    const block = { ...payload.block, status: 'resolved' as const };
    const content = language === 'en' ? 'Here is the image I created.' : '這是為你產生的圖片。';
    useChatStore.getState().updateAssistantMessage(assistantId, {
      content, answerBlocks: [block], isStreaming: false,
    });
    await databaseService.message.add(id, {
      id: assistantId, role: 'assistant', content,
      ...(!block.transient ? { answerBlocks: [block] } : {}),
    });
    logger.info('image_generation_completed', { conversationId: id, assistantId, model: block.model, persisted: !block.transient });
    return { completed: true, conversationId: id, block };
  } catch (error) {
    const content = language === 'en'
      ? 'I could not create the image. Please try again.'
      : '目前無法產生圖片，請稍後重試。';
    useChatStore.getState().updateAssistantMessage(assistantId, { content, answerBlocks: undefined, isStreaming: false });
    await databaseService.message.add(id, { id: assistantId, role: 'assistant', content });
    logger.warn('image_generation_failed', { conversationId: id, assistantId, reason: error instanceof Error ? error.name : 'UnknownError' });
    return { completed: false, conversationId: id };
  }
}
