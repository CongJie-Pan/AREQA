import 'fake-indexeddb/auto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { generateConversationImage } from '@/services/generatedImages';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { db, getCurrentUserId } from '@/database/db';
import { messageRepo } from '@/database/repositories/messageRepo';
import { useChatStore } from '@/store/chat';

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

const storedBlock = {
  type: 'image_block', imageUrl: 'https://example.test/image.png',
  provider: 'generated_image', transient: false,
};
const response = (block = storedBlock) => new Response(JSON.stringify({ block }));

describe('generated image conversation workflow', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue('user-a');
    await db.open();
    await db.messages.clear();
    await db.conversations.clear();
    useChatStore.getState().clearMessages();
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    await db.messages.clear();
    await db.messageSyncQueue.clear();
    await db.conversationSyncQueue.clear();
    await db.conversations.clear();
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

  it('records provider failure even if saving the error message also fails', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('{}', { status: 503 }));
    vi.spyOn(messageRepo, 'add').mockRejectedValueOnce(new Error('storage unavailable'));
    const result = await generateConversationImage('Draw a cat', 'conv-a', 'en', false);
    expect(result.completed).toBe(false);
    expect(useChatStore.getState().messages.at(-1)?.answerBlocks).toBeUndefined();
  });
});
