import 'fake-indexeddb/auto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Conversation, Message } from '@/database/schema';

const { rpc, from, deleteEq } = vi.hoisted(() => {
  const deleteEq = vi.fn();
  const chain = {
    delete: vi.fn(() => chain),
    eq: vi.fn((column: string, value: unknown) => { deleteEq(column, value); return chain; }),
    upsert: vi.fn(async () => ({ error: null })),
    then: (resolve: (value: { error: null }) => void) => resolve({ error: null }),
  };
  return { rpc: vi.fn(), from: vi.fn(() => chain), deleteEq };
});

vi.mock('@/lib/supabase', () => ({ supabase: { rpc, from } }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() } }));
vi.mock('@/database/db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/database/db')>();
  return { ...actual, getCurrentUserId: vi.fn(() => 'member-1') };
});

import { db } from '@/database/db';
import { syncService } from '@/services/syncService';
import { joinCollaborativeShare, syncCollaborativeConversationList } from '@/services/collaborationSync';

const SHARED_ID = '3f1c2b6e-1d2a-4c3b-9a8e-123456789abc';
const OWN_ID = '9a1c2b6e-1d2a-4c3b-9a8e-123456789abc';
const now = new Date('2026-11-19T10:00:00Z');

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: SHARED_ID,
    userId: 'member-1',
    title: 'Group study',
    createdAt: now,
    updatedAt: now,
    messageCount: 0,
    lastMessagePreview: '',
    collaboration: { role: 'editor', ownerUserId: 'owner-1' },
    ...overrides,
  };
}

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm-local',
    userId: 'member-1',
    conversationId: SHARED_ID,
    role: 'user',
    content: 'member question',
    createdAt: now,
    updatedAt: now,
    ...overrides,
  } as Message;
}

const sharedSummary = (role: 'owner' | 'editor', id = SHARED_ID) => ({
  id, title: 'Group study', kind: 'chat', role, ownerUserId: role === 'owner' ? 'member-1' : 'owner-1',
  createdAt: now.toISOString(), updatedAt: now.toISOString(),
});

describe('collaborative conversations in the normal chat', () => {
  beforeEach(async () => {
    await db.open();
  });

  afterEach(async () => {
    rpc.mockReset();
    from.mockClear();
    deleteEq.mockClear();
    await Promise.all(db.tables.map((table) => table.clear()));
  });

  it('adds participant copies, marks shared own chats and drops ended copies', async () => {
    await db.conversations.bulkPut([
      conversation({ id: OWN_ID, collaboration: undefined, title: 'Mine' }),
      conversation({ id: 'ended-1' }),
    ]);
    await db.messages.put(message({ id: 'ended-msg', conversationId: 'ended-1' }));
    rpc.mockResolvedValue({ data: [sharedSummary('editor'), sharedSummary('owner', OWN_ID)], error: null });

    expect(await syncCollaborativeConversationList('member-1')).toBe(true);

    const copy = await db.conversations.get(SHARED_ID);
    expect(copy).toEqual(expect.objectContaining({
      userId: 'member-1', title: 'Group study', collaboration: { role: 'editor', ownerUserId: 'owner-1' },
    }));
    expect((await db.conversations.get(OWN_ID))?.collaboration).toEqual({ role: 'owner', ownerUserId: 'member-1' });
    expect(await db.conversations.get('ended-1')).toBeUndefined();
    expect(await db.messages.get('ended-msg')).toBeUndefined();
  });

  it('keeps local state when the collaboration functions are unavailable', async () => {
    await db.conversations.put(conversation());
    rpc.mockResolvedValue({ data: null, error: { code: 'PGRST202' } });
    expect(await syncCollaborativeConversationList('member-1')).toBe(false);
    expect(await db.conversations.get(SHARED_ID)).toBeDefined();
  });

  it('joins a participate link and stores the local copy', async () => {
    rpc.mockImplementation(async (name: string) => (name === 'join_conversation_share'
      ? { data: SHARED_ID, error: null }
      : { data: [sharedSummary('editor')], error: null }));

    expect(await joinCollaborativeShare('L-GIo3nG6ceEijhdinSsm3A3', 'member-1', 'Group study')).toBe(SHARED_ID);
    expect(rpc).toHaveBeenCalledWith('join_conversation_share', { p_share_token: 'L-GIo3nG6ceEijhdinSsm3A3' });
    expect((await db.conversations.get(SHARED_ID))?.collaboration?.role).toBe('editor');
  });

  it('reports a failed join when the local copy cannot be created', async () => {
    rpc.mockImplementation(async (name: string) => (name === 'join_conversation_share'
      ? { data: SHARED_ID, error: null }
      : { data: null, error: { code: 'PGRST202' } }));
    expect(await joinCollaborativeShare('L-GIo3nG6ceEijhdinSsm3A3', 'member-1', 'Group study')).toBeNull();
  });

  it('pushes participant messages through the collaboration function', async () => {
    await db.conversations.put(conversation());
    rpc.mockResolvedValue({ data: 'm-local', error: null });

    await syncService.pushMessage(message({ role: 'assistant', content: 'answer', citations: ['https://example.com'] }));

    expect(rpc).toHaveBeenCalledWith('append_collaborative_message', {
      p_conversation_id: SHARED_ID,
      p_message: expect.objectContaining({ id: 'm-local', role: 'assistant', content: 'answer', citations: ['https://example.com'] }),
    });
    expect(from).not.toHaveBeenCalledWith('messages');
  });

  it('never pushes the owner row from a participant copy', async () => {
    expect(await syncService.pushConversation(conversation())).toBe(true);
    expect(from).not.toHaveBeenCalled();
  });

  it('hydrates a participant copy from the shared history', async () => {
    await db.conversations.put(conversation());
    rpc.mockResolvedValue({
      data: {
        id: SHARED_ID,
        messages: [
          { id: 'm1', role: 'user', content: 'owner question', createdAt: '2026-11-19T09:00:00Z', updatedAt: '2026-11-19T09:00:00Z' },
          { id: 'm2', role: 'assistant', content: 'answer', citations: ['https://example.com'], createdAt: '2026-11-19T09:00:05Z' },
        ],
      },
      error: null,
    });

    expect(await syncService.pullConversationMessages(SHARED_ID, 'member-1')).toBe(true);

    const stored = await db.messages.where('conversationId').equals(SHARED_ID).sortBy('createdAt');
    expect(stored.map((item) => [item.userId, item.content])).toEqual([
      ['member-1', 'owner question'],
      ['member-1', 'answer'],
    ]);
    expect(rpc).toHaveBeenCalledWith('get_collaborative_conversation', { p_conversation_id: SHARED_ID });
  });

  it('removes the local copy when access ended', async () => {
    await db.conversations.put(conversation());
    rpc.mockImplementation(async (name: string) => (name === 'get_collaborative_conversation'
      ? { data: null, error: null }
      : { data: [], error: null }));

    expect(await syncService.pullConversationMessages(SHARED_ID, 'member-1')).toBe(true);
    expect(await db.conversations.get(SHARED_ID)).toBeUndefined();
  });

  it('deletes only through the author-scoped function', async () => {
    await db.conversations.put(conversation());
    await db.messageDeletions.put({
      id: 'm-local', userId: 'member-1', conversationId: SHARED_ID, deletedAt: now, retryCount: 0, lastError: null,
    });
    rpc.mockResolvedValue({ data: true, error: null });

    expect(await syncService.deleteMessage('m-local')).toBe(true);
    expect(rpc).toHaveBeenCalledWith('delete_own_collaborative_message', {
      p_conversation_id: SHARED_ID, p_message_id: 'm-local',
    });
    expect(from).not.toHaveBeenCalledWith('messages');
  });

  it('leaves instead of deleting the owner conversation', async () => {
    await syncService.deleteConversation(SHARED_ID, conversation());
    expect(from).toHaveBeenCalledWith('conversation_members');
    expect(from).not.toHaveBeenCalledWith('conversations');
    expect(deleteEq).toHaveBeenCalledWith('user_id', 'member-1');
  });
});
