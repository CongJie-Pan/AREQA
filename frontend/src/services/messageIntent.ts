/** Shared semantic routing before text/voice or generated-image execution. */
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { getCurrentUserId } from '@/database/db';
import { useChatStore } from '@/store/chat';
import type { ImageBlock } from '@/database/schema';
import { logger } from '@/utils/logger';

export interface MessageRoute {
  createImage: boolean;
  attachments: File[];
  referenceBrief?: string;
}

/** Resolve a send using only current-account, same-conversation reference hints.
 *
 * Args:
 *   content: Original instruction, passed unchanged to the executor.
 *   conversationId: Conversation captured at send time.
 *   attachments: Current uploads; only forwarded when selected as references.
 *   signal: Cancels classification and reference downloads before execution.
 * Returns:
 *   Image execution inputs or a normal chat decision.
 * Raises:
 *   Errors for unavailable routing, invalid references, or required clarification.
 * Side Effects:
 *   Calls authenticated proxies; logs only intent/reference metadata.
 */
export async function resolveMessageRoute(
  content: string, conversationId: string | null, attachments: File[], signal: AbortSignal,
): Promise<MessageRoute> {
  const ownerId = getCurrentUserId();
  const messages = useChatStore.getState().messages.filter((message) => (
    message.userId === ownerId && message.conversationId === conversationId && !message.isStreaming
  )).slice(-6);
  const context = messages.map((message) => {
    const image = message.answerBlocks?.find((block): block is ImageBlock => block.type === 'image_block' && block.provider === 'generated_image' && Boolean(block.imageUrl));
    return { id: message.id, role: message.role, content: (image?.generationRequest?.prompt || message.content).slice(0, 1800), has_image: Boolean(image) };
  });
  const response = await authenticatedFetch('/api/images/intent', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({ prompt: content, attachment_count: attachments.length, context }),
  });
  signal.throwIfAborted();
  if (getCurrentUserId() !== ownerId) throw new Error('Message owner changed');
  if (!response.ok) throw new Error(`無法判斷此次訊息的操作，請稍後重試（${response.status}）。`);
  const result = await response.json() as { intent?: string; reference?: string; reference_message_id?: string | null };
  signal.throwIfAborted();
  if (getCurrentUserId() !== ownerId) throw new Error('Message owner changed');
  if (result.intent === 'clarify') throw new Error('請說明想畫的內容，或重新附上要參考的圖片。');
  if (result.intent === 'chat' && result.reference === 'none' && result.reference_message_id == null) {
    logger.info('message_route_selected', { intent: 'chat' });
    return { createImage: false, attachments };
  }
  if (result.intent !== 'generate_image') throw new Error('訊息操作判斷無效，請重試。');
  if (content.trim().length < 3 || content.trim().length > 1800) throw new Error('產圖要求請使用 3 至 1800 個字，較長內容可作為附件上傳。');
  logger.info('message_route_selected', { intent: result.intent, reference: result.reference });
  if (result.reference === 'attachments' && attachments.length && result.reference_message_id == null) return { createImage: true, attachments };
  if (result.reference === 'none' && result.reference_message_id == null) return { createImage: true, attachments: [] };
  if (result.reference !== 'conversation') throw new Error('找不到此次產圖的參考內容，請重新附上。');
  const reference = messages.find((message) => message.id === result.reference_message_id);
  if (!reference) throw new Error('找不到指定的參考內容，請重新附上。');
  const image = reference.answerBlocks?.find((block): block is ImageBlock => block.type === 'image_block' && block.provider === 'generated_image' && Boolean(block.imageUrl));
  if (image) {
    if (!image.storagePath?.startsWith('users/')) throw new Error('請重新附上要修改的圖片。');
    const download = await authenticatedFetch('/api/images/download', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
      body: JSON.stringify({ conversation_id: conversationId, image_id: image.slotId }),
    });
    if (!download.ok) throw new Error('無法取得參考圖片，請重新附上。');
    const blob = await download.blob();
    signal.throwIfAborted();
    if (getCurrentUserId() !== ownerId) throw new Error('Message owner changed');
    if (!blob.type.startsWith('image/') || blob.size > 5 * 1024 * 1024) throw new Error('參考圖片無法使用，請重新附上。');
    return { createImage: true, attachments: [new File([blob], 'reference-image.png', { type: blob.type })] };
  }
  if (!reference.content.trim()) throw new Error('參考內容是空的，請提供想畫的內容。');
  return { createImage: true, attachments: [], referenceBrief: reference.content.slice(0, 4000) };
}
