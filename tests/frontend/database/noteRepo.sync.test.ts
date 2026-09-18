import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { db } from '@/database/db';
import { noteRepo } from '@/database/repositories/noteRepo';
import { syncService } from '@/services/syncService';
import type { Message } from '@/database/schema';

vi.mock('@/services/syncService', () => ({
  syncService: {
    pushNote: vi.fn(),
    pushMessage: vi.fn(),
    deleteNote: vi.fn(),
  },
}));

vi.mock('@/database/db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/database/db')>();
  return {
    ...actual,
    getCurrentUserId: vi.fn(() => 'user_123'),
  };
});

const imageBlock = {
  type: 'image_block' as const,
  slotId: 'visual-1',
  topic: 'Forest plot',
  purpose: 'diagram',
  imageUrl: 'https://example.com/forest.png',
  sourceUrl: 'https://example.com/source',
  sourceDomain: 'example.com',
  caption: 'Forest plot example',
  safetyStatus: 'pass' as const,
  matchConfidence: 0.6,
};

const assistantMessage: Message = {
  id: 'assistant-note-source',
  userId: 'user_123',
  conversationId: 'conversation-note-source',
  role: 'assistant',
  content: 'A useful explanation worth saving.',
  citations: ['https://example.com/source'],
  sources: [{
    title: 'Source',
    snippet: 'Snippet',
    chunk_id: 'chunk-1',
    url: 'https://example.com/source',
  }],
  answerBlocks: [{ type: 'paragraph', text: 'A useful explanation worth saving.' }, imageBlock],
  createdAt: new Date('2026-09-09T00:00:00.000Z'),
};

describe('noteRepo sync integration', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await db.open();
    await db.notes.clear();
    await db.messages.clear();
  });

  it('saves an assistant response as one linked note and syncs it', async () => {
    const note = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');

    expect(note.messageId).toBe('assistant-note-source');
    expect(note.conversationId).toBe('conversation-note-source');
    expect(note.conversationTitle).toBe('Learning chat');
    expect(note.contentSnapshot).toBe('A useful explanation worth saving.');
    expect(note.tags).toEqual([]);
    expect(note.isPinned).toBe(false);
    expect(note.citationsSnapshot).toEqual(['https://example.com/source']);
    expect(syncService.pushNote).toHaveBeenCalledWith(expect.objectContaining({
      id: note.id,
      messageId: 'assistant-note-source',
    }));

    const notes = await noteRepo.getAll('user_123');
    expect(notes).toHaveLength(1);
  });

  it('keeps saving the same assistant response idempotent', async () => {
    const first = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');
    const second = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');

    expect(second.id).toBe(first.id);
    expect(await db.notes.count()).toBe(1);
    expect(syncService.pushNote).toHaveBeenCalledTimes(1);
  });

  it('deletes only the note and syncs the note tombstone', async () => {
    const note = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');
    vi.clearAllMocks();

    await noteRepo.delete(note.id);

    expect(await db.notes.get(note.id)).toBeUndefined();
    expect(syncService.deleteNote).toHaveBeenCalledWith(note.id);
  });

  it('updates note tags and pinned metadata with sync-safe normalized values', async () => {
    const note = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');
    vi.clearAllMocks();

    const updated = await noteRepo.updateMetadata(note.id, {
      tags: ['biology', ' Biology ', '', 'exam'],
      isPinned: true,
    });

    expect(updated.tags).toEqual(['biology', 'exam']);
    expect(updated.isPinned).toBe(true);
    expect(syncService.pushNote).toHaveBeenCalledWith(expect.objectContaining({
      id: note.id,
      tags: ['biology', 'exam'],
      isPinned: true,
    }));

    const stored = await db.notes.get(note.id);
    expect(stored?.tags).toEqual(['biology', 'exam']);
    expect(stored?.isPinned).toBe(true);
  });

  it('syncs an edited source assistant message into its linked note', async () => {
    const note = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');
    vi.clearAllMocks();

    const synced = await noteRepo.syncFromMessage({
      ...assistantMessage,
      content: 'Edited answer from chat.',
      answerBlocks: undefined,
      citations: ['https://example.com/updated'],
    });

    expect(synced?.id).toBe(note.id);
    expect(synced?.contentSnapshot).toBe('Edited answer from chat.');
    expect(synced?.answerBlocksSnapshot).toBeUndefined();
    expect(synced?.citationsSnapshot).toEqual(['https://example.com/updated']);
    expect(syncService.pushNote).toHaveBeenCalledWith(expect.objectContaining({
      id: note.id,
      contentSnapshot: 'Edited answer from chat.',
    }));
  });

  it('updates note content and mirrors it to the linked assistant message', async () => {
    await db.messages.add(assistantMessage);
    const note = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');
    vi.clearAllMocks();

    const result = await noteRepo.updateContentAndSourceMessage(note.id, 'Edited from notes.');

    expect(result.note.contentSnapshot).toBe('Edited from notes.');
    expect(result.note.answerBlocksSnapshot).toEqual([{ type: 'paragraph', text: 'Edited from notes.' }, imageBlock]);
    expect(result.sourceMessage?.content).toBe('Edited from notes.');
    expect(result.sourceMessage?.answerBlocks).toEqual([{ type: 'paragraph', text: 'Edited from notes.' }, imageBlock]);
    expect((await db.messages.get(assistantMessage.id))?.content).toBe('Edited from notes.');
    expect(syncService.pushNote).toHaveBeenCalledWith(expect.objectContaining({
      id: note.id,
      contentSnapshot: 'Edited from notes.',
    }));
    expect(syncService.pushMessage).toHaveBeenCalledWith(expect.objectContaining({
      id: assistantMessage.id,
      content: 'Edited from notes.',
      answerBlocks: [{ type: 'paragraph', text: 'Edited from notes.' }, imageBlock],
    }));
  });
});
