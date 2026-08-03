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
const { mockConversationUpsert, mockMessageUpsert } = vi.hoisted(() => ({
  mockConversationUpsert: vi.fn(),
  mockMessageUpsert: vi.fn(),
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
          upsert: mockMessageUpsert.mockResolvedValue({ error: null })
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
    mockReload.mockClear();
    mockConversationUpsert.mockClear();
    mockMessageUpsert.mockClear();
    await db.open();
    await db.conversations.clear();
    await db.messages.clear();
  });

  afterEach(async () => {
    vi.clearAllMocks();
    await db.conversations.clear();
    await db.messages.clear();
  });

  it('should not reload if cloud returns empty array', async () => {
    mockSupabaseResponse = { data: [], error: null };
    mockSupabaseMsgResponse = { data: [], error: null };

    await syncService.pullFromCloud();

    expect(mockReload).not.toHaveBeenCalled();
    const convs = await db.conversations.toArray();
    expect(convs).toHaveLength(0);
  });

  it('should save data to Dexie and reload if cloud has data', async () => {
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
          suggestions: ['請再解釋一次'],
          reasoning: { content: 'Reasoning trace', duration: 120 },
          created_at: new Date().toISOString()
        }],
        error: null
      };

      await syncService.pullFromCloud();

      expect(mockReload).toHaveBeenCalledOnce();

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
      expect(assistantMessage?.suggestions).toEqual(['請再解釋一次']);
      expect(assistantMessage?.reasoning).toEqual({ content: 'Reasoning trace', duration: 120 });
    } finally {
      setTimeoutSpy.mockRestore();
    }
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
      suggestions: ['請再解釋一次'],
      reasoning: { content: 'Reasoning trace', duration: 120 },
    }));
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
