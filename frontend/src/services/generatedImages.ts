/** Shared text and voice image generation workflow. */

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import type { ImageBlock } from '@/database/schema';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { generateUUID } from '@/utils/id';
import { logger } from '@/utils/logger';
import { filesToAttachmentMetadata } from '@/utils/attachments';

const activeImageRequests = new Set<string>();

interface ImageGenerationOptions {
  attachments?: File[];
  assistantMessageId?: string;
  referenceBrief?: string;
}

export interface GeneratedImageResult {
  completed: boolean;
  conversationId?: string;
  block?: ImageBlock;
  persisted?: boolean;
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
  options: ImageGenerationOptions = {},
): Promise<GeneratedImageResult> {
  const prompt = request.trim();
  const ownerId = getCurrentUserId();
  if (prompt.length < 3 || prompt.length > 1800 || !ownerId) {
    return { completed: false };
  }
  const conversations = useConversationStore.getState();
  let id = conversationId || conversations.activeConversationId || undefined;
  if (!id) {
    const conversation = await databaseService.conversation.create();
    if (getCurrentUserId() !== ownerId) return { completed: false };
    id = conversation.id;
    useConversationStore.setState((state) => ({ conversations: [conversation, ...state.conversations] }));
    conversations.selectConversation(id);
  }
  let referenceBrief = options.referenceBrief || '';
  if (options.attachments?.length) {
    const form = new FormData();
    form.set('prompt', prompt);
    form.set('conversation_id', id);
    form.set('interface_language', language);
    options.attachments.forEach((file) => form.append('attachments', file));
    const response = await authenticatedFetch('/api/images/reference', { method: 'POST', body: form });
    if (!response.ok) throw new Error(`Image reference preparation failed (${response.status})`);
    const prepared = await response.json() as { reference_brief?: unknown };
    if (typeof prepared.reference_brief !== 'string' || !prepared.reference_brief.trim() || prepared.reference_brief.length > 4000) {
      throw new Error('Image reference preparation returned no usable brief');
    }
    referenceBrief = prepared.reference_brief;
  }
  if (getCurrentUserId() !== ownerId) return { completed: false, conversationId: id };
  if (persistUserTurn) {
    const attachments = filesToAttachmentMetadata(options.attachments || []);
    const userId = useChatStore.getState().addUserMessage(prompt, id, attachments);
    await databaseService.message.add(id, { id: userId, role: 'user', content: prompt,
      ...(attachments.length ? { attachments } : {}) });
  }
  if (getCurrentUserId() !== ownerId) return { completed: false, conversationId: id };
  const previousMessage = options.assistantMessageId
    ? useChatStore.getState().messages.find((message) => message.id === options.assistantMessageId && message.conversationId === id)
    : undefined;
  if (options.assistantMessageId && (!previousMessage || activeImageRequests.has(options.assistantMessageId))) {
    return { completed: false, conversationId: id };
  }
  const assistantId = options.assistantMessageId || useChatStore.getState().addAssistantMessage(id);
  activeImageRequests.add(assistantId);
  const createdAt = useChatStore.getState().messages.find((message) => message.id === assistantId)?.createdAt;
  const generationRequest: NonNullable<ImageBlock['generationRequest']> = { prompt, language, referenceBrief };
  const pendingBlock: ImageBlock = {
    type: 'image_block', slotId: generateUUID(), topic: prompt.slice(0, 180),
    purpose: 'diagram', imageUrl: '', sourceUrl: '', sourceDomain: '',
    caption: language === 'en' ? 'Creating image…' : '正在產生圖片…',
    provider: 'generated_image', status: 'pending', safetyStatus: 'pass',
    matchConfidence: 1, generationRequest,
  };
  useChatStore.getState().updateAssistantMessage(assistantId, {
    content: pendingBlock.caption, isStreaming: false, answerBlocks: [pendingBlock],
  });
  logger.info('image_generation_started', { conversationId: id, assistantId, regeneration: Boolean(previousMessage), hasReference: Boolean(referenceBrief) });
  try {
    const response = await authenticatedFetch('/api/images/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, conversation_id: id, interface_language: language,
        ...(referenceBrief ? { reference_brief: referenceBrief } : {}) }),
    });
    if (!response.ok) throw new Error(`Image generation failed (${response.status})`);
    const payload = await response.json() as { block?: ImageBlock };
    if (!payload.block || payload.block.type !== 'image_block' || typeof payload.block.imageUrl !== 'string' || !payload.block.imageUrl
      || payload.block.provider !== 'generated_image' || payload.block.safetyStatus !== 'pass'
      || typeof payload.block.slotId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(payload.block.slotId)) {
      throw new Error('Image generation returned no image');
    }
    if (getCurrentUserId() !== ownerId) {
      useChatStore.getState().removeMessage(assistantId);
      logger.info('image_generation_owner_changed', { conversationId: id, assistantId });
      return { completed: false, conversationId: id };
    }
    const block = { ...payload.block, generationRequest, status: 'resolved' as const };
    const content = block.transient
      ? language === 'en' ? 'The image is ready, but could not be saved. Please download it now.' : '圖片已完成，但目前無法儲存。請先下載圖片。'
      : language === 'en' ? 'Here is the image I created.' : '這是為你產生的圖片。';
    useChatStore.getState().updateAssistantMessage(assistantId, {
      content, answerBlocks: [block], isStreaming: false,
    });
    try {
      const savedBlock = block.transient
        ? { ...block, imageUrl: '', thumbnailUrl: '', transient: false, status: 'error' as const, caption: content }
        : block;
      const messageData = { role: 'assistant' as const, content, answerBlocks: [savedBlock] };
      if (previousMessage) await databaseService.message.update(assistantId, messageData);
      else await databaseService.message.add(id, { id: assistantId, createdAt, ...messageData });
      logger.info('image_generation_completed', { conversationId: id, assistantId, persisted: !block.transient });
      return { completed: true, conversationId: id, block, persisted: !block.transient };
    } catch (error) {
      const unsavedContent = language === 'en'
        ? 'The image is ready, but could not be saved. Please download it now.'
        : '圖片已完成，但目前無法儲存。請先下載圖片。';
      useChatStore.getState().updateAssistantMessage(assistantId, { content: unsavedContent });
      logger.warn('image_generation_persistence_failed', { conversationId: id, assistantId, reason: error instanceof Error ? error.name : 'UnknownError' });
      return { completed: true, conversationId: id, block, persisted: false };
    }
  } catch (error) {
    if (getCurrentUserId() !== ownerId) {
      useChatStore.getState().removeMessage(assistantId);
      return { completed: false, conversationId: id };
    }
    const content = language === 'en'
      ? 'I could not create the image. Please try again.'
      : '目前無法產生圖片，請稍後重試。';
    const previousImage = previousMessage?.answerBlocks?.some((block) => block.type === 'image_block' && block.imageUrl);
    if (previousMessage && previousImage) {
      useChatStore.getState().updateAssistantMessage(assistantId, previousMessage);
      logger.warn('image_regeneration_failed_previous_retained', { conversationId: id, assistantId });
      throw error;
    }
    const errorBlock: ImageBlock = { ...pendingBlock, status: 'error', caption: content };
    useChatStore.getState().updateAssistantMessage(assistantId, { content, answerBlocks: [errorBlock], isStreaming: false });
    try {
      const messageData = { role: 'assistant' as const, content, answerBlocks: [errorBlock] };
      if (previousMessage) await databaseService.message.update(assistantId, messageData);
      else await databaseService.message.add(id, { id: assistantId, createdAt, ...messageData });
    } catch (persistenceError) {
      logger.warn('image_generation_failure_persistence_failed', { conversationId: id, assistantId, reason: persistenceError instanceof Error ? persistenceError.name : 'UnknownError' });
    }
    logger.warn('image_generation_failed', { conversationId: id, assistantId, reason: error instanceof Error ? error.name : 'UnknownError' });
    return { completed: false, conversationId: id };
  } finally {
    activeImageRequests.delete(assistantId);
  }
}

/** Regenerate in place, retaining the original image intent and reference brief. */
export async function regenerateConversationImage(assistantMessageId: string): Promise<void> {
  const messages = useChatStore.getState().messages;
  const targetIndex = messages.findIndex((message) => message.id === assistantMessageId);
  const target = messages[targetIndex];
  const image = target?.answerBlocks?.find((block): block is ImageBlock => block.type === 'image_block' && block.provider === 'generated_image');
  if (!image || image.status === 'pending' || activeImageRequests.has(assistantMessageId)) return;
  if (target.userId !== getCurrentUserId()) throw new Error('Image conversation owner changed');
  const previousUser = messages.slice(0, targetIndex).reverse().find((message) => message.role === 'user' && message.conversationId === target.conversationId);
  const request = image.generationRequest;
  const prompt = request?.prompt || previousUser?.content;
  if (!prompt) throw new Error('Original image request is unavailable');
  await generateConversationImage(prompt, target.conversationId, request?.language || 'zh-TW', false, {
    assistantMessageId, referenceBrief: request?.referenceBrief,
  });
}
