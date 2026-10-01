/** Shared text and voice image generation workflow. */

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import type { ImageBlock } from '@/database/schema';
import { useChatStore, type DisplayMessage } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { generateUUID } from '@/utils/id';
import { logger } from '@/utils/logger';
import { filesToAttachmentMetadata } from '@/utils/attachments';

const activeImageRequests = new Set<string>();
const imageRequestControllers = new Map<string, AbortController>();

/** Stop awaiting cancelled work even if a transport delivers a late response. */
function awaitImageOperation<T>(operation: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      signal.removeEventListener('abort', onAbort);
      reject(signal.reason);
    };
    signal.addEventListener('abort', onAbort, { once: true });
    operation.then((value) => {
      signal.removeEventListener('abort', onAbort);
      if (signal.aborted) reject(signal.reason);
      else resolve(value);
    }, (error) => {
      signal.removeEventListener('abort', onAbort);
      reject(error);
    });
    if (signal.aborted) onAbort();
  });
}

function clearImageRequest(requestId: string): void {
  useChatStore.setState((state) => {
    if (!state.imageGenerationRequests[requestId]) return state;
    const requests = { ...state.imageGenerationRequests };
    delete requests[requestId];
    return { imageGenerationRequests: requests };
  });
}

/** Cancel image jobs belonging to the current account and selected conversation.
 *
 * Args:
 *   conversationId: Selected conversation, or null while a new one is prepared.
 * Returns:
 *   Whether an active image request was stopped.
 * Side Effects:
 *   Aborts client work and immediately releases composer state. The provider may
 *   continue server-side; late results cannot update or persist an image card.
 */
export function cancelConversationImage(conversationId: string | null): boolean {
  let cancelled = false;
  for (const [requestId, request] of Object.entries(useChatStore.getState().imageGenerationRequests)) {
    if (request.userId !== getCurrentUserId() || request.conversationId !== conversationId) continue;
    const controller = imageRequestControllers.get(requestId);
    if (!controller) continue;
    controller.abort();
    clearImageRequest(requestId);
    cancelled = true;
  }
  return cancelled;
}

interface ImageGenerationOptions {
  attachments?: File[];
  assistantMessageId?: string;
  referenceBrief?: string;
  conversationContext?: string;
  replaceExistingText?: boolean;
}

function imageConversationContext(messages: DisplayMessage[], conversationId: string): string {
  return messages
    .filter((message) => message.conversationId === conversationId
      && (message.role === 'user' || message.role === 'assistant')
      && !message.isStreaming && message.content.trim())
    .slice(-6)
    .map((message) => `${message.role}: ${message.content.trim().slice(0, 280)}`)
    .join('\n')
    .slice(-2000);
}

export interface GeneratedImageResult {
  completed: boolean;
  cancelled?: boolean;
  errorCode?: string;
  conversationId?: string;
  block?: ImageBlock;
  persisted?: boolean;
}

/** Generate an image with an immediate placeholder and cancellable lifecycle.
 *
 * Args:
 *   request: The user's explicit drawing request.
 *   conversationId: Existing conversation, if one has been selected.
 *   language: Label language for the generated visual.
 *   persistUserTurn: Whether to record a new user turn.
 *   options: Attachments or the original message/reference brief for regeneration.
 * Returns:
 *   Completion, cancellation, and persistence details after updating the card.
 * Raises:
 *   Provider/preparation errors when regenerating an existing image; the old
 *   image remains visible. New-turn failures are represented by retryable cards.
 * Side Effects:
 *   Tracks image jobs separately from text/voice streams, calls authenticated
 *   proxies, and persists metadata. Lifecycle logs contain IDs and safe flags
 *   only; prompt text, reference content, and credentials are never logged.
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
  if (prompt.length < 3 || prompt.length > 1800 || !ownerId) return { completed: false };

  const conversations = useConversationStore.getState();
  let id = conversationId || conversations.activeConversationId || undefined;
  const previousMessage: DisplayMessage | undefined = options.assistantMessageId
    ? useChatStore.getState().messages.find((message) => message.id === options.assistantMessageId && message.conversationId === id)
    : undefined;
  if (options.assistantMessageId && (!previousMessage || activeImageRequests.has(options.assistantMessageId))) {
    return { completed: false, conversationId: id };
  }
  // Regeneration replaces the image capability's output, retaining requested analysis.
  const retainedBlocks = (options.replaceExistingText ? [] : previousMessage?.answerBlocks ?? []).filter(
    (block) => !(block.type === 'image_block' && block.provider === 'generated_image'),
  );
  const retainedText = retainedBlocks.flatMap((block) => block.type === 'paragraph' ? [block.text] : []).join('\n\n');
  const withStatus = (status: string) => [retainedText, status].filter(Boolean).join('\n\n');

  const requestId = generateUUID();
  const controller = new AbortController();
  const { signal } = controller;
  imageRequestControllers.set(requestId, controller);
  useChatStore.setState((state) => ({ imageGenerationRequests: {
    ...state.imageGenerationRequests,
    [requestId]: { userId: ownerId, conversationId: id || null, assistantMessageId: options.assistantMessageId || null },
  } }));
  let assistantId = options.assistantMessageId;
  if (assistantId) activeImageRequests.add(assistantId);
  let createdAt: Date | undefined;
  let isFirstTurn = false;
  let referenceBrief = options.attachments?.length ? '' : options.referenceBrief || '';
  let conversationContext = options.conversationContext || '';
  let generationRequest: NonNullable<ImageBlock['generationRequest']> = {
    prompt, language, referenceBrief, conversationContext,
    ...(options.attachments?.length ? { requiresReference: true } : {}),
  };
  const pendingBlock: ImageBlock = {
    type: 'image_block', slotId: generateUUID(), topic: prompt.slice(0, 180),
    purpose: 'diagram', imageUrl: '', sourceUrl: '', sourceDomain: '',
    caption: language === 'en' ? 'Preparing image…' : language === 'zh-CN' ? '正在准备图片…' : '正在準備圖片…',
    provider: 'generated_image', status: 'pending', safetyStatus: 'pass',
    matchConfidence: 1, generationRequest,
  };
  const showPending = () => {
    if (assistantId) useChatStore.getState().updateAssistantMessage(assistantId, {
      content: retainedText || pendingBlock.caption, createdAt, isStreaming: false, answerBlocks: [...retainedBlocks, { ...pendingBlock }],
    });
  };
  const ownerChanged = () => {
    if (getCurrentUserId() === ownerId) return false;
    if (assistantId) useChatStore.getState().removeMessage(assistantId);
    logger.info('image_generation_owner_changed', { conversationId: id, assistantId, requestId });
    return true;
  };

  try {
    if (!id) {
      const conversation = await awaitImageOperation(databaseService.conversation.create(), signal);
      signal.throwIfAborted();
      if (ownerChanged()) return { completed: false };
      id = conversation.id;
      useConversationStore.setState((state) => ({ conversations: [conversation, ...state.conversations] }));
      conversations.selectConversation(id);
    }
    if (ownerChanged()) return { completed: false, conversationId: id };
    if (!options.assistantMessageId) {
      conversationContext = imageConversationContext(useChatStore.getState().messages, id);
      generationRequest = { ...generationRequest, conversationContext };
      pendingBlock.generationRequest = generationRequest;
    }
    isFirstTurn = persistUserTurn && !previousMessage && !useChatStore.getState().messages.some(
      (message) => message.conversationId === id,
    );
    const attachments = filesToAttachmentMetadata(options.attachments || []);
    const userId = persistUserTurn ? useChatStore.getState().addUserMessage(prompt, id, attachments) : undefined;
    const userCreatedAt = useChatStore.getState().messages.find((message) => message.id === userId)?.createdAt;
    assistantId = assistantId || useChatStore.getState().addAssistantMessage(id);
    activeImageRequests.add(assistantId);
    createdAt = useChatStore.getState().messages.find((message) => message.id === assistantId)?.createdAt;
    // IndexedDB sorts equal timestamps by UUID; keep this turn ordered on reload.
    if (userCreatedAt && createdAt && createdAt.getTime() <= userCreatedAt.getTime()) {
      createdAt = new Date(userCreatedAt.getTime() + 1);
    }
    showPending();
    useChatStore.setState((state) => ({ imageGenerationRequests: {
      ...state.imageGenerationRequests,
      [requestId]: { userId: ownerId, conversationId: id!, assistantMessageId: assistantId! },
    } }));
    logger.info('image_generation_started', { conversationId: id, assistantId, requestId, regeneration: Boolean(previousMessage), hasReference: Boolean(referenceBrief || options.attachments?.length) });

    // Render the card before disk/network work so attachment preparation is visible.
    if (userId) {
      await awaitImageOperation(databaseService.message.add(id, { id: userId, createdAt: userCreatedAt, role: 'user', content: prompt,
        ...(attachments.length ? { attachments } : {}) }), signal);
      signal.throwIfAborted();
      if (ownerChanged()) return { completed: false, conversationId: id };
    }
    if (options.attachments?.length) {
      pendingBlock.caption = language === 'en' ? 'Preparing image references…' : language === 'zh-CN' ? '正在整理参考附件…' : '正在整理參考附件…';
      showPending();
      const form = new FormData();
      form.set('prompt', prompt);
      form.set('conversation_id', id);
      form.set('interface_language', language);
      options.attachments.forEach((file) => form.append('attachments', file));
      const response = await awaitImageOperation(authenticatedFetch('/api/images/reference', { method: 'POST', body: form, signal }), signal);
      if (!response.ok) throw new Error(`Image reference preparation failed (${response.status})`);
      const prepared = await awaitImageOperation(response.json(), signal) as { reference_brief?: unknown };
      signal.throwIfAborted();
      if (typeof prepared.reference_brief !== 'string' || !prepared.reference_brief.trim() || prepared.reference_brief.length > 4000) {
        throw new Error('Image reference preparation returned no usable brief');
      }
      referenceBrief = prepared.reference_brief;
      generationRequest = { ...generationRequest, referenceBrief };
      pendingBlock.generationRequest = generationRequest;
      if (ownerChanged()) return { completed: false, conversationId: id };
    }
    signal.throwIfAborted();
    pendingBlock.caption = language === 'en' ? 'Creating image…' : language === 'zh-CN' ? '正在产生图片…' : '正在產生圖片…';
    showPending();
    const response = await awaitImageOperation(authenticatedFetch('/api/images/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
      body: JSON.stringify({ prompt, conversation_id: id, interface_language: language,
        ...(conversationContext ? { conversation_context: conversationContext } : {}),
        ...(referenceBrief ? { reference_brief: referenceBrief } : {}) }),
    }), signal);
    if (!response.ok) {
      const failure = await response.json().catch(() => null) as { code?: unknown } | null;
      const code = typeof failure?.code === 'string' && /^IMAGE_[A-Z0-9_]+$/.test(failure.code)
        ? failure.code : `IMAGE_HTTP_${response.status}`;
      throw Object.assign(new Error(`Image generation failed (${code})`), { code });
    }
    const payload = await awaitImageOperation(response.json(), signal) as { block?: ImageBlock };
    signal.throwIfAborted();
    if (!payload.block || payload.block.type !== 'image_block' || typeof payload.block.imageUrl !== 'string' || !payload.block.imageUrl
      || payload.block.provider !== 'generated_image' || payload.block.safetyStatus !== 'pass'
      || typeof payload.block.slotId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(payload.block.slotId)) {
      throw new Error('Image generation returned no image');
    }
    if (ownerChanged()) return { completed: false, conversationId: id };
    const block = { ...payload.block, generationRequest, status: 'resolved' as const };
    const warning = block.transient
      ? language === 'en' ? 'The image is ready, but could not be saved. Please download it now.' : '圖片已完成，但目前無法儲存。請先下載圖片。'
      : '';
    const content = withStatus(warning);
    useChatStore.getState().updateAssistantMessage(assistantId, { content, answerBlocks: [...retainedBlocks, block], isStreaming: false });
    // Once the result is published, Stop must not race its persistence.
    clearImageRequest(requestId);
    try {
      const savedBlock = block.transient
        ? { ...block, imageUrl: '', thumbnailUrl: '', transient: false, status: 'error' as const, caption: warning }
        : block;
      const messageData = { role: 'assistant' as const, content, answerBlocks: [...retainedBlocks, savedBlock] };
      if (previousMessage) await databaseService.message.update(assistantId, messageData);
      else await databaseService.message.add(id, { id: assistantId, createdAt, ...messageData });
      if (isFirstTurn && !block.transient && !ownerChanged()) {
        // Reuse title persistence without delaying image completion or regeneration.
        logger.info('image_generation_title_started', { conversationId: id, assistantId });
        void useConversationStore.getState().generateTitle(id, [{ role: 'user', content: prompt }]).catch((titleError) => {
          logger.warn('image_generation_title_failed', { conversationId: id, reason: titleError instanceof Error ? titleError.name : 'UnknownError' });
        });
      }
      logger.info('image_generation_completed', { conversationId: id, assistantId, requestId, persisted: !block.transient });
      return { completed: true, conversationId: id, block, persisted: !block.transient };
    } catch (error) {
      const unsavedContent = language === 'en'
        ? 'The image is ready, but could not be saved. Please download it now.'
        : '圖片已完成，但目前無法儲存。請先下載圖片。';
      if (!ownerChanged()) useChatStore.getState().updateAssistantMessage(assistantId, { content: withStatus(unsavedContent) });
      logger.warn('image_generation_persistence_failed', { conversationId: id, assistantId, requestId, reason: error instanceof Error ? error.name : 'UnknownError' });
      return { completed: true, conversationId: id, block, persisted: false };
    }
  } catch (error) {
    if (ownerChanged()) return { completed: false, conversationId: id };
    const cancelled = signal.aborted;
    const code = error instanceof Error && 'code' in error && typeof error.code === 'string'
      ? error.code : 'IMAGE_GENERATION_FAILED';
    const content = cancelled
      ? language === 'en' ? 'Image generation stopped.' : language === 'zh-CN' ? '已停止生成图片。' : '已停止生成圖片。'
      : language === 'en' ? `Image generation failed (${code}).` : `產圖失敗（${code}）。`;
    clearImageRequest(requestId);
    logger[cancelled ? 'info' : 'warn'](cancelled ? 'image_generation_cancelled' : 'image_generation_failed', {
      conversationId: id, assistantId, requestId, reason: cancelled ? 'AbortError' : error instanceof Error ? error.name : 'UnknownError',
    });
    // Without a card, the caller must surface setup failure and restore the draft.
    if (!assistantId && !cancelled) throw error;
    const previousImage = previousMessage?.answerBlocks?.some((block) => block.type === 'image_block' && block.imageUrl);
    if (previousMessage && previousImage) {
      useChatStore.getState().updateAssistantMessage(assistantId!, previousMessage);
      if (!cancelled) throw error;
    } else if (assistantId && id) {
      const errorBlock: ImageBlock = { ...pendingBlock, status: 'error', caption: content };
      const failureContent = cancelled ? withStatus(content) : retainedText;
      useChatStore.getState().updateAssistantMessage(assistantId, { content: failureContent, answerBlocks: [...retainedBlocks, errorBlock], isStreaming: false });
      try {
        const messageData = { role: 'assistant' as const, content: failureContent, answerBlocks: [...retainedBlocks, errorBlock] };
        if (previousMessage) await databaseService.message.update(assistantId, messageData);
        else await databaseService.message.add(id, { id: assistantId, createdAt, ...messageData });
      } catch (persistenceError) {
        logger.warn('image_generation_failure_persistence_failed', { conversationId: id, assistantId, requestId, reason: persistenceError instanceof Error ? persistenceError.name : 'UnknownError' });
      }
    }
    return { completed: false, conversationId: id, ...(cancelled ? { cancelled: true } : { errorCode: code }) };
  } finally {
    if (assistantId) activeImageRequests.delete(assistantId);
    imageRequestControllers.delete(requestId);
    clearImageRequest(requestId);
  }
}

/** Regenerate in place, retaining the original image intent and reference brief.
 *
 * Args:
 *   assistantMessageId: Image card to replace when generation succeeds.
 * Raises:
 *   Errors for ownership changes, missing intent, or incomplete references.
 * Side Effects:
 *   Starts a cancellable job; cancellation or provider failure retains the old
 *   image. Incomplete attachment preparation requires resending the files.
 */
export async function regenerateConversationImage(assistantMessageId: string): Promise<void> {
  const messages = useChatStore.getState().messages;
  const targetIndex = messages.findIndex((message) => message.id === assistantMessageId);
  const target = messages[targetIndex];
  const image = target?.answerBlocks?.find((block): block is ImageBlock => block.type === 'image_block' && block.provider === 'generated_image');
  if (!image || image.status === 'pending' || activeImageRequests.has(assistantMessageId)) return;
  if (target.userId !== getCurrentUserId()) throw new Error('Image conversation owner changed');
  const previousUser = messages.slice(0, targetIndex).reverse().find((message) => message.role === 'user' && message.conversationId === target.conversationId);
  const request = image.generationRequest;
  if ((request?.requiresReference || previousUser?.attachments?.length) && !request?.referenceBrief) {
    throw new Error('Please resend the image request with its reference attachments');
  }
  const prompt = request?.prompt || previousUser?.content;
  if (!prompt) throw new Error('Original image request is unavailable');
  await generateConversationImage(prompt, target.conversationId, request?.language || 'zh-TW', false, {
    assistantMessageId, referenceBrief: request?.referenceBrief,
    conversationContext: request?.conversationContext,
  });
}
