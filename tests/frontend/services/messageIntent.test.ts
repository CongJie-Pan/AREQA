import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resolveMessageRoute } from '@/services/messageIntent';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { useChatStore } from '@/store/chat';
import { getCurrentUserId } from '@/database/db';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/database/db', () => ({ getCurrentUserId: vi.fn(() => 'user-a') }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn() } }));
const decision = (intent: string, reference = 'none', reference_message_id: string | null = null) => new Response(JSON.stringify({ intent, reference, reference_message_id }));
const run = (text = '幫我產圖', files: File[] = [], signal = new AbortController().signal) => resolveMessageRoute(text, 'conv-a', files, signal);

describe('semantic send routing contract', () => {
  afterEach(() => { vi.useRealTimers(); });
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue('user-a');
    useChatStore.setState({ messages: [] });
  });

  it('routes an untagged generation decision with the current uploaded image', async () => {
    const file = new File(['png'], 'source.png', { type: 'image/png' });
    vi.mocked(authenticatedFetch).mockResolvedValue(decision('generate_image', 'attachments'));
    expect(await run('幫我產圖', [file])).toEqual({ createImage: true, attachments: [file] });
    expect(JSON.parse(String(vi.mocked(authenticatedFetch).mock.calls[0][1]?.body))).toEqual({
      prompt: '幫我產圖', attachment_count: 1, context: [],
    });
  });

  it.each(['請解釋這張圖', '不要產圖，只寫 prompt', '為什麼不能產圖'])('preserves a chat decision for %s', async (text) => {
    vi.mocked(authenticatedFetch).mockResolvedValue(decision('chat'));
    expect(await run(text)).toEqual({ createImage: false, attachments: [] });
  });

  it('routes a self-contained image request without adding unrelated uploads', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(decision('generate_image'));
    expect(await run('請畫一隻貓', [new File(['notes'], 'notes.txt')])).toEqual({ createImage: true, attachments: [] });
  });

  it('selects same-account conversation text as a bounded reference', async () => {
    useChatStore.setState({ messages: [
      { id: 'source', userId: 'user-a', conversationId: 'conv-a', role: 'assistant', content: 'Photosynthesis', createdAt: new Date() },
      { id: 'other', userId: 'user-a', conversationId: 'other-conv', role: 'assistant', content: 'PRIVATE OTHER CHAT', createdAt: new Date() },
      { id: 'other-user', userId: 'user-b', conversationId: 'conv-a', role: 'assistant', content: 'PRIVATE OTHER OWNER', createdAt: new Date() },
    ] });
    vi.mocked(authenticatedFetch).mockResolvedValue(decision('generate_image', 'conversation', 'source'));
    expect(await run('請根據上面畫教學圖')).toEqual({ createImage: true, attachments: [], referenceBrief: 'Photosynthesis' });
    const body = String(vi.mocked(authenticatedFetch).mock.calls[0][1]?.body);
    expect(body).not.toContain('PRIVATE');
  });

  it('downloads a selected generated image through the authenticated proxy before using it as a reference', async () => {
    useChatStore.setState({ messages: [{ id: 'image-turn', userId: 'user-a', conversationId: 'conv-a', role: 'assistant', content: '', createdAt: new Date(), answerBlocks: [{
      type: 'image_block', slotId: 'image-a', topic: 'cat', purpose: 'diagram', imageUrl: 'https://example.test/private.png',
      sourceUrl: '', sourceDomain: '', caption: 'cat', safetyStatus: 'pass', matchConfidence: 1, provider: 'generated_image',
      storagePath: 'users/user-a/image.png', generationRequest: { prompt: 'Draw a cat', language: 'en' },
    }] }] });
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(decision('generate_image', 'conversation', 'image-turn'))
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { headers: { 'Content-Type': 'image/png' } }));
    const result = await run('把剛才那張改成水彩');
    expect(result.attachments[0]).toBeInstanceOf(File);
    expect(result.attachments[0].type).toBe('image/png');
    expect(authenticatedFetch).toHaveBeenLastCalledWith('/api/images/download', expect.objectContaining({ body: JSON.stringify({ conversation_id: 'conv-a', image_id: 'image-a' }) }));
    expect(String(vi.mocked(authenticatedFetch).mock.calls[0][1]?.body)).not.toContain('private.png');
  });

  it.each([decision('clarify'), decision('generate_image', 'conversation', 'missing'), decision('invalid')])('rejects ambiguous or invalid decisions instead of silently sending text', async (response) => {
    vi.mocked(authenticatedFetch).mockResolvedValue(response);
    await expect(run()).rejects.toThrow();
  });

  it.each([404, 429, 500, 502, 503, 504])('continues ordinary text when optional classification returns %s', async (status) => {
    const file = new File(['lesson'], 'lesson.txt', { type: 'text/plain' });
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('', { status }));
    expect(await run('你好，請解釋什麼是效果量', [file])).toEqual({ createImage: false, attachments: [file] });
  });

  it('continues ordinary text after a classifier network failure', async () => {
    vi.mocked(authenticatedFetch).mockRejectedValue(new TypeError('Failed to fetch'));
    expect(await run('請說明統計顯著性的意思')).toEqual({ createImage: false, attachments: [] });
  });

  it('continues ordinary text after a malformed classifier response', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('invalid json'));
    expect(await run('你好')).toEqual({ createImage: false, attachments: [] });
  });

  it.each([400, 401, 403])('does not bypass authentication or validation failures (%s)', async (status) => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('', { status }));
    await expect(run('你好')).rejects.toThrow(String(status));
  });

  it('never falls back to sending after cancellation during classifier failure', async () => {
    const controller = new AbortController();
    vi.mocked(authenticatedFetch).mockImplementation(async () => { controller.abort(); throw new TypeError('Failed to fetch'); });
    await expect(run('你好', [], controller.signal)).rejects.toThrow();
  });

  it('never falls back to sending after an account switch during classifier failure', async () => {
    vi.mocked(authenticatedFetch).mockImplementation(async () => { vi.mocked(getCurrentUserId).mockReturnValue('user-b'); throw new TypeError('Failed to fetch'); });
    await expect(run('你好')).rejects.toThrow('owner changed');
  });

  it('keeps an implicit image modification explicit during classifier failure', async () => {
    useChatStore.setState({ messages: [{ id: 'image-turn', userId: 'user-a', conversationId: 'conv-a', role: 'assistant', content: '', createdAt: new Date(), answerBlocks: [{
      type: 'image_block', slotId: 'image-a', topic: 'cat', purpose: 'diagram', imageUrl: 'https://example.test/image.png',
      sourceUrl: '', sourceDomain: '', caption: 'cat', safetyStatus: 'pass', matchConfidence: 1, provider: 'generated_image',
    }] }] });
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('', { status: 503 }));
    await expect(run('改成紅色')).rejects.toThrow('503');
  });

  it('releases ordinary text after four seconds even if classification never settles', async () => {
    vi.useFakeTimers();
    let finish!: (value: Response) => void;
    vi.mocked(authenticatedFetch).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const work = run('你好');
    const requestSignal = vi.mocked(authenticatedFetch).mock.calls[0][1]?.signal;
    await vi.advanceTimersByTimeAsync(4000);
    expect(await work).toEqual({ createImage: false, attachments: [] });
    expect(requestSignal?.aborted).toBe(true);
    finish(decision('generate_image'));
    await Promise.resolve();
    expect(authenticatedFetch).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('settles cancellation immediately when the classifier ignores abort', async () => {
    vi.mocked(authenticatedFetch).mockImplementation(() => new Promise(() => {}));
    const controller = new AbortController();
    const work = run('你好', [], controller.signal);
    controller.abort();
    await expect(work).rejects.toThrow();
  });

  it('bounds image classification without changing it into a text send', async () => {
    vi.useFakeTimers();
    vi.mocked(authenticatedFetch).mockImplementation(() => new Promise(() => {}));
    const work = run('幫我產圖');
    const assertion = expect(work).rejects.toThrow('逾時');
    await vi.advanceTimersByTimeAsync(15000);
    await assertion;
    expect(vi.getTimerCount()).toBe(0);
  });

  it('surfaces unavailable routing instead of executing a different action', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('', { status: 503 }));
    await expect(run()).rejects.toThrow('503');
  });

  it('never executes a late decision after cancellation', async () => {
    const controller = new AbortController();
    vi.mocked(authenticatedFetch).mockImplementation(async () => { controller.abort(); return decision('generate_image'); });
    await expect(run('請畫一隻貓', [], controller.signal)).rejects.toThrow();
  });

  it('rejects a decision after an account switch', async () => {
    vi.mocked(authenticatedFetch).mockImplementation(async () => { vi.mocked(getCurrentUserId).mockReturnValue('user-b'); return decision('generate_image'); });
    await expect(run('請畫一隻貓')).rejects.toThrow('owner changed');
  });
});
