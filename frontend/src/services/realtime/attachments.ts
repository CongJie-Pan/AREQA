import { API_CONFIG } from '@/config/api';
import { authenticatedFetch } from '@/services/authenticatedFetch';

export interface VoiceMaterialContext {
  title: string;
  text: string;
  truncated: boolean;
}

export interface PreparedVoiceAttachment {
  conversation_id: string;
  version: string;
  material: VoiceMaterialContext;
}

export async function prepareVoiceAttachments(
  conversationId: string,
  files: File[],
): Promise<PreparedVoiceAttachment> {
  const form = new FormData();
  form.set('conversation_id', conversationId);
  files.forEach((file) => form.append('attachments', file));
  const response = await authenticatedFetch(API_CONFIG.realtimeAttachmentsEndpoint, {
    method: 'POST',
    body: form,
  });
  if (response.status === 422) {
    throw new Error('即時語音目前支援 TXT、Markdown 和含文字的 PDF 檔案。');
  }
  if (!response.ok) throw new Error(`Voice attachment preparation failed (${response.status})`);
  const result = await response.json() as PreparedVoiceAttachment;
  if (result.conversation_id !== conversationId || !result.material?.text || !result.version) {
    throw new Error('Voice attachment preparation returned invalid context');
  }
  return result;
}

export async function loadVoiceMaterial(conversationId: string): Promise<VoiceMaterialContext | null> {
  const response = await authenticatedFetch(API_CONFIG.realtimeContextEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, messages: [] }),
  });
  if (!response.ok) return null;
  const result = await response.json() as {
    conversation_id?: string;
    speaking_material?: VoiceMaterialContext | null;
  };
  return result.conversation_id === conversationId && result.speaking_material?.text
    ? result.speaking_material
    : null;
}
