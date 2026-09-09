import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { db } from '@/database/db';
import { noteRepo } from '@/database/repositories/noteRepo';
import { syncService } from '@/services/syncService';
import type { Message } from '@/database/schema';

vi.mock('@/services/syncService', () => ({
  syncService: {
    pushNote: vi.fn(),
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
  answerBlocks: [{ type: 'paragraph', text: 'A useful explanation worth saving.' }],
  createdAt: new Date('2026-09-09T00:00:00.000Z'),
};

describe('noteRepo sync integration', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await db.open();
    await db.notes.clear();
  });

  it('saves an assistant response as one linked note and syncs it', async () => {
    const note = await noteRepo.addFromMessage(assistantMessage, 'Learning chat');

    expect(note.messageId).toBe('assistant-note-source');
    expect(note.conversationId).toBe('conversation-note-source');
    expect(note.conversationTitle).toBe('Learning chat');
    expect(note.contentSnapshot).toBe('A useful explanation worth saving.');
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
});
