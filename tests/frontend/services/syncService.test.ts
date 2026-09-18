import 'fake-indexeddb/auto';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { syncService } from '@/services/syncService';
import { db } from '@/database/db';
import { supabase } from '@/lib/supabase';
import type { Message } from '@/database/schema';

// Mock dependencies
const mockReload = vi.fn();
Object.defineProperty(window, 'location', {
  value: { reload: mockReload },
  writable: true
});

// Mock logger to avoid cluttering test output
vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn()
  }
}));

// Mock getCurrentUserId
vi.mock('@/database/db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/database/db')>();
  return {
    ...actual,
    getCurrentUserId: vi.fn(() => 'user_123'),
  };
});

// Create a variable to control what supabase returns
let mockSupabaseResponse: any = { data: [], error: null };
let mockSupabaseMsgResponse: any = { data: [], error: null };
let mockSupabaseNoteResponse: any = { data: [], error: null };
const { mockConversationUpsert, mockMessageUpsert, mockNoteUpsert } = vi.hoisted(() => ({
  mockConversationUpsert: vi.fn(),
  mockMessageUpsert: vi.fn(),
  mockNoteUpsert: vi.fn(),
}));
const { mockMessageDelete, mockMessageDeleteEq, mockNoteDelete, mockNoteDeleteEq } = vi.hoisted(() => ({
  mockMessageDelete: vi.fn(),
  mockMessageDeleteEq: vi.fn(),
  mockNoteDelete: vi.fn(),
  mockNoteDeleteEq: vi.fn(),
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: vi.fn().mockImplementation((table) => {
      if (table === 'conversations') {
        return {
          select: vi.fn().mockReturnThis(),
          eq: vi.fn().mockResolvedValue(mockSupabaseResponse),
          upsert: mockConversationUpsert.mockResolvedValue({ error: null }),
          delete: vi.fn().mockReturnThis()
        };
      }
      if (table === 'messages') {
        return {
          select: vi.fn().mockReturnThis(),
          eq: vi.fn().mockResolvedValue(mockSupabaseMsgResponse),
          upsert: mockMessageUpsert.mockResolvedValue({ error: null }),
          delete: mockMessageDelete
        };
      }
      if (table === 'notes') {
        return {
          select: vi.fn().mockReturnThis(),
          eq: vi.fn().mockResolvedValue(mockSupabaseNoteResponse),
          upsert: mockNoteUpsert.mockResolvedValue({ error: null }),
          delete: mockNoteDelete
        };
      }
      return {
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockResolvedValue({ data: [], error: null })
      };
    })
  }
}));

describe('syncService - pullFromCloud', () => {
  beforeEach(async () => {
    mockSupabaseResponse = { data: [], error: null };
    mockSupabaseMsgResponse = { data: [], error: null };
    mockSupabaseNoteResponse = { data: [], error: null };
    mockReload.mockClear();
    mockConversationUpsert.mockClear();
    mockMessageUpsert.mockClear();
    mockNoteUpsert.mockClear();
    mockMessageDelete.mockClear();
    mockMessageDeleteEq.mockClear();
    mockNoteDelete.mockClear();
    mockNoteDeleteEq.mockClear();
    mockMessageDelete.mockReturnValue({ eq: mockMessageDeleteEq });
    mockMessageDeleteEq.mockReturnValue({ eq: mockMessageDeleteEq });
    mockNoteDelete.mockReturnValue({ eq: mockNoteDeleteEq });
    mockNoteDeleteEq.mockReturnValue({ eq: mockNoteDeleteEq });
    await db.open();
    await db.conversations.clear();
    await db.messages.clear();
    await db.notes.clear();
  });

  afterEach(async () => {
    vi.clearAllMocks();
    await db.conversations.clear();
    await db.messages.clear();
    await db.notes.clear();
  });

  it('should not reload if cloud returns empty array', async () => {
    mockSupabaseResponse = { data: [], error: null };
    mockSupabaseMsgResponse = { data: [], error: null };
    mockSupabaseNoteResponse = { data: [], error: null };

    await syncService.pullFromCloud();

    expect(mockReload).not.toHaveBeenCalled();
    const convs = await db.conversations.toArray();
    expect(convs).toHaveLength(0);
  });

  it('should save cloud data to Dexie without forcing a page reload', async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation(((callback: TimerHandler, _delay?: number, ...args: unknown[]) => {
      if (typeof callback === 'function') {
        callback(...args);
      }
      return 0 as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout);

    try {
      mockSupabaseResponse = {
        data: [{
          id: 'conv_1',
          user_id: 'user_123',
          title: 'Test',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }],
        error: null
      };

      mockSupabaseMsgResponse = {
        data: [{
          id: 'msg_1',
          user_id: 'user_123',
          conversation_id: 'conv_1',
          role: 'user',
          content: 'Hi',
          attachments: [{ name: 'lesson.pdf', mediaType: 'application/pdf', sizeBytes: 2048 }],
          created_at: new Date().toISOString()
        },
        {
          id: 'msg_2',
          user_id: 'user_123',
          conversation_id: 'conv_1',
          role: 'assistant',
          content: 'Hello',
          citations: ['https://example.com/source'],
          search_results: [{ title: 'Source', url: 'https://example.com/source', snippet: 'Search snippet' }],
          sources: [{
            title: 'Structured Source',
            snippet: 'Structured source snippet.',
            score: 0.97,
            chunk_id: 'https://example.com/source',
            url: 'https://example.com/source',
          }],
          answer_blocks: [
            { type: 'paragraph', text: 'Hello' },
            {
              type: 'image_block',
              slotId: 'visual-1',
              topic: 'Forest plot',
              purpose: 'diagram',
              imageUrl: 'https://example.com/forest.png',
              sourceUrl: 'https://example.com/source',
              sourceDomain: 'example.com',
              caption: 'Forest plot example',
              safetyStatus: 'pass',
              matchConfidence: 0.6,
            },
          ],
          suggestions: ['請再解釋一次'],
          reasoning: { content: 'Reasoning trace', duration: 120 },
          created_at: new Date().toISOString()
        }],
        error: null
      };
      mockSupabaseNoteResponse = {
        data: [{
          id: 'note_1',
          user_id: 'user_123',
          conversation_id: 'conv_1',
          message_id: 'msg_2',
          conversation_title: 'Test',
          content_snapshot: 'Hello',
          citations_snapshot: ['https://example.com/source'],
          sources_snapshot: [{
            title: 'Structured Source',
            snippet: 'Structured source snippet.',
            score: 0.97,
            chunk_id: 'https://example.com/source',
            url: 'https://example.com/source',
          }],
          answer_blocks_snapshot: [{ type: 'paragraph', text: 'Hello' }],
          tags: ['biology', 'exam'],
          is_pinned: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }],
        error: null,
      };

      await syncService.pullFromCloud();

      expect(mockReload).not.toHaveBeenCalled();

      const convs = await db.conversations.toArray();
      expect(convs).toHaveLength(1);
      expect(convs[0].id).toBe('conv_1');
      // Ensure messageCount is correctly computed
      expect(convs[0].messageCount).toBe(2);

      const msgs = await db.messages.toArray();
      expect(msgs).toHaveLength(2);
      expect(msgs.find((message) => message.id === 'msg_1')?.attachments).toEqual([
        { name: 'lesson.pdf', mediaType: 'application/pdf', sizeBytes: 2048 },
      ]);
      const assistantMessage = msgs.find((message) => message.id === 'msg_2');
      expect(assistantMessage?.citations).toEqual(['https://example.com/source']);
      expect(assistantMessage?.searchResults).toEqual([
        { title: 'Source', url: 'https://example.com/source', snippet: 'Search snippet' },
      ]);
      expect(assistantMessage?.sources).toEqual([{
        title: 'Structured Source',
        snippet: 'Structured source snippet.',
        score: 0.97,
        chunk_id: 'https://example.com/source',
        url: 'https://example.com/source',
      }]);
      expect(assistantMessage?.answerBlocks).toEqual([
        { type: 'paragraph', text: 'Hello' },
        {
          type: 'image_block',
          slotId: 'visual-1',
          topic: 'Forest plot',
          purpose: 'diagram',
          imageUrl: 'https://example.com/forest.png',
          sourceUrl: 'https://example.com/source',
          sourceDomain: 'example.com',
          caption: 'Forest plot example',
          safetyStatus: 'pass',
          matchConfidence: 0.6,
        },
      ]);
      expect(assistantMessage?.suggestions).toEqual(['請再解釋一次']);
      expect(assistantMessage?.reasoning).toEqual({ content: 'Reasoning trace', duration: 120 });

      const notes = await db.notes.toArray();
      expect(notes).toHaveLength(1);
      expect(notes[0]).toEqual(expect.objectContaining({
        id: 'note_1',
        conversationId: 'conv_1',
        messageId: 'msg_2',
        contentSnapshot: 'Hello',
        tags: ['biology', 'exam'],
        isPinned: true,
      }));
    } finally {
      setTimeoutSpy.mockRestore();
    }
  });

  it('clears local answer blocks when the cloud row explicitly stores null', async () => {
    const createdAt = new Date('2026-08-03T00:00:00.000Z');
    await db.conversations.add({
      id: 'conv_clear_blocks',
      userId: 'user_123',
      title: 'Editable answer',
      createdAt,
      updatedAt: createdAt,
      messageCount: 1,
      lastMessagePreview: 'Edited answer',
    });
    await db.messages.add({
      id: 'msg_clear_blocks',
      userId: 'user_123',
      conversationId: 'conv_clear_blocks',
      role: 'assistant',
      content: 'Edited answer',
      answerBlocks: [{ type: 'paragraph', text: 'Old structured answer' }],
      createdAt,
    });

    mockSupabaseResponse = {
      data: [{
        id: 'conv_clear_blocks',
        user_id: 'user_123',
        title: 'Editable answer',
        created_at: createdAt.toISOString(),
        updated_at: createdAt.toISOString(),
      }],
      error: null,
    };
    mockSupabaseMsgResponse = {
      data: [{
        id: 'msg_clear_blocks',
        user_id: 'user_123',
        conversation_id: 'conv_clear_blocks',
        role: 'assistant',
        content: 'Edited answer',
        answer_blocks: null,
        created_at: createdAt.toISOString(),
      }],
      error: null,
    };

    await syncService.pullFromCloud();

    expect((await db.messages.get('msg_clear_blocks'))?.answerBlocks).toBeUndefined();
  });

  it('should push reference metadata to cloud messages', async () => {
    const message: Message = {
      id: 'msg_reference',
      userId: 'user_123',
      conversationId: 'conv_1',
      role: 'assistant',
      content: 'Answer with sources',
      citations: ['https://example.com/source'],
      searchResults: [{ title: 'Source', url: 'https://example.com/source', snippet: 'Search snippet' }],
      sources: [{
        title: 'Structured Source',
        snippet: 'Structured source snippet.',
        score: 0.97,
        chunk_id: 'https://example.com/source',
        url: 'https://example.com/source',
      }],
      answerBlocks: [
        { type: 'paragraph', text: 'Answer with sources' },
      ],
      suggestions: ['請再解釋一次'],
      reasoning: { content: 'Reasoning trace', duration: 120 },
      createdAt: new Date('2026-08-03T00:00:00.000Z'),
    };

    await syncService.pushMessage(message);

    expect(supabase.from).toHaveBeenCalledWith('messages');
    expect(mockMessageUpsert).toHaveBeenCalledWith(expect.objectContaining({
      id: 'msg_reference',
      citations: ['https://example.com/source'],
      search_results: [{ title: 'Source', url: 'https://example.com/source', snippet: 'Search snippet' }],
      sources: [{
        title: 'Structured Source',
        snippet: 'Structured source snippet.',
        score: 0.97,
        chunk_id: 'https://example.com/source',
        url: 'https://example.com/source',
      }],
      answer_blocks: [
        { type: 'paragraph', text: 'Answer with sources' },
      ],
      suggestions: ['請再解釋一次'],
      reasoning: { content: 'Reasoning trace', duration: 120 },
    }));
  });

  it('logs message upsert errors returned by Supabase', async () => {
    const { logger } = await import('@/utils/logger');
    mockMessageUpsert.mockResolvedValueOnce({ error: new Error('upsert failed') });

    await syncService.pushMessage({
      id: 'msg_upsert_error',
      userId: 'user_123',
      conversationId: 'conv_1',
      role: 'assistant',
      content: 'Answer',
      createdAt: new Date('2026-08-03T00:00:00.000Z'),
    });

    expect(logger.error).toHaveBeenCalledWith(
      'Push message error',
      expect.any(Error),
      expect.objectContaining({
        component: 'syncService',
        messageId: 'msg_upsert_error',
      }),
    );
  });

  it('should delete one cloud message scoped to the current user', async () => {
    await syncService.deleteMessage('assistant_old');

    expect(supabase.from).toHaveBeenCalledWith('messages');
    expect(mockMessageDelete).toHaveBeenCalledOnce();
    expect(mockMessageDeleteEq).toHaveBeenNthCalledWith(1, 'id', 'assistant_old');
    expect(mockMessageDeleteEq).toHaveBeenNthCalledWith(2, 'user_id', 'user_123');
  });

  it('should push and delete notes scoped to the current user', async () => {
    await syncService.pushNote({
      id: 'note_cloud',
      userId: 'user_123',
      conversationId: 'conv_1',
      messageId: 'assistant_1',
      conversationTitle: 'Notes chat',
      contentSnapshot: 'Saved assistant response',
      citationsSnapshot: ['https://example.com/source'],
      answerBlocksSnapshot: [{ type: 'paragraph', text: 'Saved assistant response' }],
      tags: ['biology', 'exam'],
      isPinned: true,
      createdAt: new Date('2026-09-09T00:00:00.000Z'),
      updatedAt: new Date('2026-09-09T00:00:01.000Z'),
    });

    expect(supabase.from).toHaveBeenCalledWith('notes');
    expect(mockNoteUpsert).toHaveBeenCalledWith(expect.objectContaining({
      id: 'note_cloud',
      user_id: 'user_123',
      conversation_id: 'conv_1',
      message_id: 'assistant_1',
      content_snapshot: 'Saved assistant response',
      tags: ['biology', 'exam'],
      is_pinned: true,
    }));

    await syncService.deleteNote('note_cloud');

    expect(mockNoteDelete).toHaveBeenCalledOnce();
    expect(mockNoteDeleteEq).toHaveBeenNthCalledWith(1, 'id', 'note_cloud');
    expect(mockNoteDeleteEq).toHaveBeenNthCalledWith(2, 'user_id', 'user_123');
  });

  it('should preserve local reference metadata when legacy cloud rows omit it', async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation(((callback: TimerHandler, _delay?: number, ...args: unknown[]) => {
      if (typeof callback === 'function') {
        callback(...args);
      }
      return 0 as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout);

    try {
      const createdAt = new Date('2026-08-03T00:00:00.000Z');
      await db.conversations.add({
        id: 'conv_legacy',
        userId: 'user_123',
        title: 'Legacy cloud row',
        createdAt,
        updatedAt: createdAt,
        messageCount: 1,
        lastMessagePreview: 'Answer with local sources',
      });
      await db.messages.add({
        id: 'msg_legacy',
        userId: 'user_123',
        conversationId: 'conv_legacy',
        role: 'assistant',
        content: 'Answer with local sources',
        citations: ['https://example.com/local'],
        sources: [{
          title: 'Local Source',
          snippet: 'Local source snippet.',
          chunk_id: 'https://example.com/local',
          url: 'https://example.com/local',
        }],
        createdAt,
      });

      mockSupabaseResponse = {
        data: [{
          id: 'conv_legacy',
          user_id: 'user_123',
          title: 'Legacy cloud row',
          created_at: createdAt.toISOString(),
          updated_at: new Date('2026-08-03T00:01:00.000Z').toISOString(),
        }],
        error: null,
      };
      mockSupabaseMsgResponse = {
        data: [{
          id: 'msg_legacy',
          user_id: 'user_123',
          conversation_id: 'conv_legacy',
          role: 'assistant',
          content: 'Answer with local sources',
          feedback: 'liked',
          created_at: createdAt.toISOString(),
        }],
        error: null,
      };

      await syncService.pullFromCloud();

      const message = await db.messages.get('msg_legacy');
      expect(message?.feedback).toBe('liked');
      expect(message?.citations).toEqual(['https://example.com/local']);
      expect(message?.sources).toEqual([{
        title: 'Local Source',
        snippet: 'Local source snippet.',
        chunk_id: 'https://example.com/local',
        url: 'https://example.com/local',
      }]);
    } finally {
      setTimeoutSpy.mockRestore();
    }
  });

  it('should log error and not reload on network failure', async () => {
    mockSupabaseResponse = { data: null, error: new Error('Network error') };
    
    const { logger } = await import('@/utils/logger');

    await syncService.pullFromCloud();

    expect(mockReload).not.toHaveBeenCalled();
    expect(logger.error).toHaveBeenCalled();
  });
});
