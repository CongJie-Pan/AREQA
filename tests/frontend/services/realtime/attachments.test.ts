import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { loadVoiceMaterial, prepareVoiceAttachments } from '@/services/realtime/attachments';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));

describe('voice attachment preparation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uploads files without starting a text answer and returns prepared context', async () => {
    const file = new File(['The unique finding is cobalt.'], 'notes.txt', { type: 'text/plain' });
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({
      conversation_id: 'conv_voice', version: 'v1',
      material: { title: 'notes.txt', text: 'The unique finding is cobalt.', truncated: false },
    }), { status: 200 }));

    const result = await prepareVoiceAttachments('conv_voice', [file]);

    expect(result.material.text).toContain('cobalt');
    const [url, init] = vi.mocked(authenticatedFetch).mock.calls[0];
    expect(url).toBe('/api/realtime/attachments');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get('conversation_id')).toBe('conv_voice');
    expect((init?.body as FormData).get('attachments')).toBe(file);
  });

  it('does not present a different conversation’s material as ready', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({
      conversation_id: 'another_conversation',
      speaking_material: { title: 'secret.txt', text: 'unrelated content', truncated: false },
    }), { status: 200 }));

    expect(await loadVoiceMaterial('conv_voice')).toBeNull();
  });

  it('rejects a failed upload before it can be shown as available', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('unavailable', { status: 503 }));

    await expect(prepareVoiceAttachments('conv_voice', [new File(['text'], 'notes.txt')]))
      .rejects.toThrow('Voice attachment preparation failed (503)');
  });

  it('explains when the file cannot be read in voice mode', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('unsupported', { status: 422 }));

    await expect(prepareVoiceAttachments('conv_voice', [new File(['image'], 'photo.png')]))
      .rejects.toThrow('即時語音目前支援 TXT、Markdown 和含文字的 PDF 檔案。');
  });
});
