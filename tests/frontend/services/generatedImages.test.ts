import 'fake-indexeddb/auto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cancelConversationImage, generateConversationImage, regenerateConversationImage } from '@/services/generatedImages';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { db, getCurrentUserId } from '@/database/db';
import { messageRepo } from '@/database/repositories/messageRepo';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { databaseService } from '@/services/database';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: vi.fn(() => 'user-a'),
}));
vi.mock('@/services/database', async () => ({
  databaseService: {
    message: (await import('@/database/repositories/messageRepo')).messageRepo,
    conversation: { create: vi.fn() },
  },
}));
vi.mock('@/services/syncService', () => ({
  syncService: { pushMessage: vi.fn(async () => true), pushConversation: vi.fn(async () => true) },
}));

const storedBlock = {
  type: 'image_block', slotId: 'image-a', imageUrl: 'https://example.test/image.png', safetyStatus: 'pass',
  provider: 'generated_image', transient: false,
};
const response = (block = storedBlock) => new Response(JSON.stringify({ block }));

describe('generated image conversation workflow', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    vi.spyOn(useConversationStore.getState(), 'generateTitle').mockResolvedValue();
    vi.mocked(getCurrentUserId).mockReturnValue('user-a');
    await db.open();
    await db.messages.clear();
    await db.conversations.clear();
    useChatStore.getState().clearMessages();
    useChatStore.getState().resetStreamingState();
    useConversationStore.setState({ activeConversationId: null, conversations: [] });
  });

  it('generates a title from the first image prompt but not subsequent images or regeneration', async () => {
    vi.mocked(authenticatedFetch).mockImplementation(async () => response());
    vi.mocked(databaseService.conversation.create).mockResolvedValue({
      id: 'new-image-conv', userId: 'user-a', title: 'New Chat', createdAt: new Date(), updatedAt: new Date(), messageCount: 0,
    });
    expect((await generateConversationImage('請畫細胞結構', undefined, 'zh-TW')).completed).toBe(true);
    expect(useConversationStore.getState().generateTitle).toHaveBeenCalledExactlyOnceWith(
      'new-image-conv', [{ role: 'user', content: '請畫細胞結構' }],
    );
    const assistantId = useChatStore.getState().messages.at(-1)!.id;
    await regenerateConversationImage(assistantId);
    await generateConversationImage('請畫另一張細胞圖', 'new-image-conv', 'zh-TW');
    expect(useConversationStore.getState().generateTitle).toHaveBeenCalledOnce();
  });

  it('keeps a completed image when background title generation fails', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(response());
    vi.mocked(useConversationStore.getState().generateTitle).mockRejectedValueOnce(new Error('Title unavailable'));
    expect(await generateConversationImage('Draw a cat', 'conv-a', 'en')).toMatchObject({ completed: true, persisted: true });
    expect(useChatStore.getState().messages.at(-1)?.answerBlocks?.[0]).toMatchObject({ status: 'resolved' });
  });

  it('sends recent same-conversation text to image generation and retains it for retries', async () => {
    vi.mocked(authenticatedFetch).mockImplementation(async () => response());
    useChatStore.getState().addUserMessage('Use a blue book and a small cat.', 'conv-a');
    useChatStore.getState().addUserMessage('Unrelated red car.', 'conv-b');
    await generateConversationImage('Draw the scene we discussed', 'conv-a', 'en');
    const body = JSON.parse(vi.mocked(authenticatedFetch).mock.calls[0][1]?.body as string);
    expect(body.conversation_context).toContain('blue book');
    expect(body.conversation_context).not.toContain('red car');
    expect(body.conversation_context).not.toContain('Draw the scene we discussed');
    const image = useChatStore.getState().messages.at(-1)!.answerBlocks![0];
    expect(image).toMatchObject({ generationRequest: { conversationContext: body.conversation_context } });
    await regenerateConversationImage(useChatStore.getState().messages.at(-1)!.id);
    const retryBody = JSON.parse(vi.mocked(authenticatedFetch).mock.calls[1][1]?.body as string);
    expect(retryBody.conversation_context).toBe(body.conversation_context);
  });

  it('does not title failed image generations', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('', { status: 503 }));
    await generateConversationImage('Draw a cat', 'conv-a', 'en');
    expect(useConversationStore.getState().generateTitle).not.toHaveBeenCalled();
  });

  it('shows a provider code on the image error card without a text reply', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({ code: 'IMAGE_PROVIDER_HTTP_402' }), { status: 503 }));
    await generateConversationImage('Draw a cat', 'conv-a', 'en');
    const failure = useChatStore.getState().messages.at(-1)!;
    expect(failure.content).toBe('');
    expect(failure.answerBlocks?.[0]).toMatchObject({ status: 'error', caption: 'IMAGE_PROVIDER_HTTP_402' });
  });

  it('renders a preparation card and marks the composer busy before user persistence completes', async () => {
    let saveUser!: () => void;
    const originalAdd = messageRepo.add.bind(messageRepo);
    vi.spyOn(messageRepo, 'add').mockImplementationOnce(async (...args) => {
      await new Promise<void>((resolve) => { saveUser = resolve; });
      return originalAdd(...args);
    });
    vi.mocked(authenticatedFetch).mockResolvedValue(response());
    useChatStore.setState({ isStreaming: true, currentStreamingId: 'text-stream' });
    const work = generateConversationImage('Draw a cat', 'conv-a', 'en');
    expect(useChatStore.getState().messages.at(-1)).toMatchObject({
      content: 'Preparing image…', isStreaming: false, answerBlocks: [{ status: 'pending' }],
    });
    expect(Object.values(useChatStore.getState().imageGenerationRequests)).toEqual([
      expect.objectContaining({ conversationId: 'conv-a', userId: 'user-a' }),
    ]);
    expect(authenticatedFetch).not.toHaveBeenCalled();
    saveUser();
    expect((await work).completed).toBe(true);
    expect(useChatStore.getState().imageGenerationRequests).toEqual({});
    expect(useChatStore.getState()).toMatchObject({ isStreaming: true, currentStreamingId: 'text-stream' });
  });

  it('stops a request immediately and never publishes or saves a late provider result', async () => {
    let finish!: (result: Response) => void;
    vi.mocked(authenticatedFetch).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const work = generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    const signal = vi.mocked(authenticatedFetch).mock.calls[0][1]?.signal;
    expect(cancelConversationImage('conv-a')).toBe(true);
    expect(signal?.aborted).toBe(true);
    expect(useChatStore.getState().imageGenerationRequests).toEqual({});
    expect(await work).toMatchObject({ completed: false, cancelled: true });
    const stopped = useChatStore.getState().messages.at(-1)!;
    expect(stopped).toMatchObject({ content: 'Image generation stopped.', answerBlocks: [{ status: 'error', imageUrl: '' }] });
    finish(response());
    await Promise.resolve();
    expect(useChatStore.getState().messages.at(-1)).toEqual(stopped);
    expect((await db.messages.get(stopped.id))?.answerBlocks?.[0]).toMatchObject({ status: 'error', imageUrl: '' });
  });

  it('can stop while preparing a new conversation without selecting its late result', async () => {
    let finish!: (conversation: Awaited<ReturnType<typeof databaseService.conversation.create>>) => void;
    vi.mocked(databaseService.conversation.create).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const work = generateConversationImage('Draw a cat', undefined, 'en');
    expect(Object.values(useChatStore.getState().imageGenerationRequests)).toEqual([
      { userId: 'user-a', conversationId: null, assistantMessageId: null },
    ]);
    expect(cancelConversationImage(null)).toBe(true);
    expect(await work).toMatchObject({ completed: false, cancelled: true });
    finish({ id: 'late-conv', userId: 'user-a', title: 'New', createdAt: new Date(), updatedAt: new Date(), messageCount: 0 });
    await Promise.resolve();
    expect(useConversationStore.getState().activeConversationId).toBeNull();
    expect(useChatStore.getState().messages).toEqual([]);
    expect(authenticatedFetch).not.toHaveBeenCalled();
  });

  it('stops attachment preparation without generating an image from late reference data', async () => {
    let finish!: (result: Response) => void;
    vi.mocked(authenticatedFetch).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const work = generateConversationImage('Explain this attachment', 'conv-a', 'en', false, {
      attachments: [new File(['source'], 'lesson.txt')],
    });
    expect(useChatStore.getState().messages.at(-1)?.content).toBe('Preparing image references…');
    expect(cancelConversationImage('conv-a')).toBe(true);
    expect(await work).toMatchObject({ cancelled: true });
    finish(new Response(JSON.stringify({ reference_brief: 'Late reference' })));
    await Promise.resolve();
    expect(authenticatedFetch).toHaveBeenCalledOnce();
    const stopped = useChatStore.getState().messages.at(-1)!;
    await expect(regenerateConversationImage(stopped.id)).rejects.toThrow('reference attachments');
    expect(authenticatedFetch).toHaveBeenCalledOnce();
  });

  it('cancels only the selected conversation and does not clear another active job', async () => {
    vi.mocked(authenticatedFetch).mockImplementation(() => new Promise(() => {}));
    const first = generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    const second = generateConversationImage('Draw a dog', 'conv-b', 'en', false);
    vi.mocked(getCurrentUserId).mockReturnValue('user-b');
    expect(cancelConversationImage('conv-a')).toBe(false);
    vi.mocked(getCurrentUserId).mockReturnValue('user-a');
    expect(cancelConversationImage('conv-a')).toBe(true);
    await first;
    expect(Object.values(useChatStore.getState().imageGenerationRequests)).toEqual([
      expect.objectContaining({ conversationId: 'conv-b' }),
    ]);
    expect(cancelConversationImage('conv-b')).toBe(true);
    await second;
    expect(useChatStore.getState().imageGenerationRequests).toEqual({});
  });

  it('preserves the original image when regeneration is stopped', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(response());
    await generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    const original = useChatStore.getState().messages.at(-1)!;
    let finish!: (result: Response) => void;
    vi.mocked(authenticatedFetch).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const work = regenerateConversationImage(original.id);
    expect(cancelConversationImage('conv-a')).toBe(true);
    await work;
    finish(response({ ...storedBlock, imageUrl: 'https://example.test/late.png' }));
    await Promise.resolve();
    expect(useChatStore.getState().messages.at(-1)).toEqual(original);
    expect((await db.messages.get(original.id))?.answerBlocks?.[0]).toMatchObject({ imageUrl: storedBlock.imageUrl });
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    await db.messages.clear();
    await db.messageSyncQueue.clear();
    await db.conversationSyncQueue.clear();
    await db.conversations.clear();
  });

  it('preserves user-before-image ordering when both placeholders are created in the same millisecond', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-29T00:00:00Z'));
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(response());
    await generateConversationImage('Draw a cat', 'conv-a', 'en');
    const saved = await messageRepo.getByConversationId('conv-a', 'user-a');
    expect(saved.map((message) => message.role)).toEqual(['user', 'assistant']);
    expect(saved[1].createdAt.getTime()).toBeGreaterThan(saved[0].createdAt.getTime());
  });

  it('releases preparation state and surfaces conversation creation failure to the caller', async () => {
    vi.mocked(databaseService.conversation.create).mockRejectedValueOnce(new Error('storage unavailable'));
    await expect(generateConversationImage('Draw a cat', undefined, 'en')).rejects.toThrow('storage unavailable');
    expect(useChatStore.getState().imageGenerationRequests).toEqual({});
    expect(useChatStore.getState().messages).toEqual([]);
    expect(authenticatedFetch).not.toHaveBeenCalled();
  });

  it('does not save a result under a different account when sign-in changes during generation', async () => {
    let finish!: (result: Response) => void;
    vi.mocked(authenticatedFetch).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const work = generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    const pendingId = useChatStore.getState().messages.at(-1)?.id;
    vi.mocked(getCurrentUserId).mockReturnValue('user-b');
    finish(response());
    expect((await work).completed).toBe(false);
    expect(await db.messages.toArray()).toEqual([]);
    expect(useChatStore.getState().messages.some((message) => message.id === pendingId)).toBe(false);
  });

  it('keeps the placeholder position after later turns are saved and the conversation reloads', async () => {
    let finish!: (result: Response) => void;
    vi.mocked(authenticatedFetch).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const work = generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    const placeholder = useChatStore.getState().messages.at(-1);
    expect(placeholder).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 10));
    await messageRepo.add('conv-a', { id: 'later-turn', role: 'user', content: 'Continue explaining' });
    await new Promise((resolve) => setTimeout(resolve, 10));
    finish(response());
    expect((await work).completed).toBe(true);
    const saved = await messageRepo.getByConversationId('conv-a', 'user-a');
    expect(saved.map((message) => message.id)).toEqual([placeholder?.id, 'later-turn']);
    expect(saved[0]?.createdAt).toEqual(placeholder?.createdAt);
  });

  it('keeps a generated image visible if saving its message fails', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(response());
    vi.spyOn(messageRepo, 'add').mockRejectedValueOnce(new Error('storage unavailable'));
    const result = await generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    expect(result).toMatchObject({ completed: true, persisted: false });
    expect(useChatStore.getState().messages.at(-1)?.answerBlocks?.[0]).toMatchObject({ imageUrl: storedBlock.imageUrl });
    expect(useChatStore.getState().messages.at(-1)?.content).toContain('could not be saved');
  });

  it('saves successful image replies without a completion preamble and retains the generation intent', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(response());
    const result = await generateConversationImage('畫一張統計教學圖', 'conv-a', 'en', false);
    expect(result.completed).toBe(true);
    const message = useChatStore.getState().messages.at(-1)!;
    expect(message.content).toBe('');
    const saved = await db.messages.get(message.id);
    expect(saved?.content).toBe('');
    expect(saved?.answerBlocks?.[0]).toMatchObject({ generationRequest: { prompt: '畫一張統計教學圖' } });
  });

  it('records provider failure even if saving the error message also fails', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('{}', { status: 503 }));
    vi.spyOn(messageRepo, 'add').mockRejectedValueOnce(new Error('storage unavailable'));
    const result = await generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    expect(result.completed).toBe(false);
    expect(useChatStore.getState().messages.at(-1)?.answerBlocks?.[0]).toMatchObject({
      provider: 'generated_image', status: 'error', generationRequest: { prompt: 'Draw a cat' },
    });
  });

  it('compiles attachments before generating and keeps the brief for retries', async () => {
    vi.mocked(authenticatedFetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ reference_brief: 'Cells use sunlight to make sugar.' })))
      .mockResolvedValueOnce(response());
    const file = new File(['Photosynthesis source'], 'lesson.txt', { type: 'text/plain' });
    const result = await generateConversationImage('Explain this attachment', 'conv-a', 'en', true, { attachments: [file] });
    expect(result.completed).toBe(true);
    expect(authenticatedFetch).toHaveBeenNthCalledWith(1, '/api/images/reference', expect.objectContaining({ body: expect.any(FormData) }));
    const generationBody = JSON.parse(vi.mocked(authenticatedFetch).mock.calls[1][1]?.body as string);
    expect(generationBody.reference_brief).toBe('Cells use sunlight to make sugar.');
    const saved = await db.messages.toArray();
    expect(saved.find((item) => item.role === 'user')?.attachments?.[0].name).toBe('lesson.txt');
    expect(saved.find((item) => item.role === 'assistant')?.answerBlocks?.[0]).toMatchObject({
      generationRequest: { prompt: 'Explain this attachment', referenceBrief: generationBody.reference_brief },
    });
  });

  it('does not make an ungrounded image when reference preparation fails', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('{}', { status: 503 }));
    const result = await generateConversationImage('Explain this attachment', 'conv-a', 'en', true, {
      attachments: [new File(['source'], 'lesson.txt')],
    });
    expect(result.completed).toBe(false);
    expect(authenticatedFetch).toHaveBeenCalledOnce();
    const failed = useChatStore.getState().messages.at(-1)!;
    expect(failed.answerBlocks?.[0]).toMatchObject({ status: 'error' });
    expect(useChatStore.getState().imageGenerationRequests).toEqual({});
    await expect(regenerateConversationImage(failed.id)).rejects.toThrow('reference attachments');
    expect(authenticatedFetch).toHaveBeenCalledOnce();
  });

  it('ignores regeneration while an image is pending, then regenerates in place using the saved intent', async () => {
    let finish!: (result: Response) => void;
    vi.mocked(authenticatedFetch).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const work = generateConversationImage('Draw a cat', 'conv-a', 'en', false, { referenceBrief: 'A cat beside a book.' });
    const id = useChatStore.getState().messages.at(-1)!.id;
    await regenerateConversationImage(id);
    expect(authenticatedFetch).toHaveBeenCalledOnce();
    finish(response());
    await work;
    vi.mocked(authenticatedFetch).mockResolvedValue(response({ ...storedBlock, imageUrl: 'https://example.test/replacement.png' }));
    await regenerateConversationImage(id);
    expect(authenticatedFetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(vi.mocked(authenticatedFetch).mock.calls[1][1]?.body as string)).toMatchObject({
      prompt: 'Draw a cat', reference_brief: 'A cat beside a book.', interface_language: 'en',
    });
    expect(useChatStore.getState().messages).toHaveLength(1);
    expect((await db.messages.toArray())).toHaveLength(1);
    expect((await db.messages.get(id))?.answerBlocks?.[0]).toMatchObject({ imageUrl: 'https://example.test/replacement.png' });
  });

  it('retains the previous image if regeneration fails', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(response());
    await generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    const original = useChatStore.getState().messages.at(-1)!;
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('{}', { status: 503 }));
    await expect(regenerateConversationImage(original.id)).rejects.toThrow('failed');
    expect(useChatStore.getState().messages.at(-1)).toEqual(original);
    expect((await db.messages.get(original.id))?.answerBlocks?.[0]).toMatchObject({ imageUrl: storedBlock.imageUrl });
  });

  it.each([true, false])('retains mixed analysis when retrying a failed image (success=%s)', async (success) => {
    const id = useChatStore.getState().addAssistantMessage('conv-a');
    const paragraph = { type: 'paragraph' as const, text: '統計顯著不代表效果重要。' };
    const image = { ...storedBlock, type: 'image_block' as const, safetyStatus: 'pass' as const,
      status: 'error' as const, imageUrl: '', generationRequest: { prompt: 'Draw a cat', language: 'en' as const } };
    useChatStore.getState().updateAssistantMessage(id, { content: paragraph.text, answerBlocks: [paragraph, image] });
    await messageRepo.add('conv-a', { id, role: 'assistant', content: paragraph.text, answerBlocks: [paragraph, image] });
    vi.mocked(authenticatedFetch).mockImplementationOnce(async () => {
      const pending = useChatStore.getState().messages.find((message) => message.id === id)!;
      expect(pending.content).toBe(paragraph.text);
      expect(pending.answerBlocks).toEqual([paragraph, expect.objectContaining({ status: 'pending' })]);
      return success ? response() : new Response('{}', { status: 503 });
    });
    await regenerateConversationImage(id);
    const visible = useChatStore.getState().messages.find((message) => message.id === id)!;
    expect(visible.content).toContain(paragraph.text);
    expect(visible.answerBlocks).toEqual([paragraph, expect.objectContaining({ status: success ? 'resolved' : 'error' })]);
    expect((await db.messages.get(id))?.answerBlocks).toEqual(visible.answerBlocks);
    expect(useChatStore.getState().messages).toHaveLength(1);
  });

  it('keeps failed requests retryable instead of silently accepting an incomplete 200 response', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({ block: { type: 'image_block' } })));
    expect((await generateConversationImage('Draw a cat', 'conv-a', 'en', false)).completed).toBe(false);
    const failed = useChatStore.getState().messages.at(-1)!;
    expect(failed.content).toBe('');
    expect(failed.answerBlocks?.[0]).toMatchObject({ status: 'error', caption: 'IMAGE_GENERATION_FAILED',
      generationRequest: { prompt: 'Draw a cat' } });
    vi.mocked(authenticatedFetch).mockResolvedValue(response());
    await regenerateConversationImage(failed.id);
    expect(useChatStore.getState().messages).toHaveLength(1);
    expect((await db.messages.get(failed.id))?.answerBlocks?.[0]).toMatchObject({ status: 'resolved' });
  });
});
