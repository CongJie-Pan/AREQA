import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { updateUser: vi.fn() } } }));

import { db } from '@/database/db';
import { detectUnusedFeatureSteps } from '@/services/onboardingFeatures';

const now = new Date('2026-11-15T00:00:00.000Z');

describe('detectUnusedFeatureSteps', () => {
  beforeEach(async () => {
    await db.open();
    await Promise.all([db.notes.clear(), db.conversations.clear(), db.messages.clear()]);
  });

  it('offers every feature to a learner who only chatted', async () => {
    await db.messages.add({ id: 'm1', userId: 'u1', conversationId: 'c1', role: 'user', content: 'hi', createdAt: now });
    expect(await detectUnusedFeatureSteps('u1')).toEqual(['addNote', 'replyMore', 'composerPlus']);
  });

  it('skips features the learner already used', async () => {
    await db.notes.add({ id: 'n1', userId: 'u1', conversationId: 'c1', messageId: 'm2', content: 'note', createdAt: now, updatedAt: now, isPinned: false, tags: [] } as never);
    await db.conversations.add({ id: 'c2', userId: 'u1', title: 'branch', createdAt: now, updatedAt: now, messageCount: 0, lastMessagePreview: '', branchOrigin: { conversationId: 'c1', messageId: 'm2', title: 't', copiedMessageId: 'x' } } as never);
    await db.messages.add({ id: 'm3', userId: 'u1', conversationId: 'c1', role: 'user', content: 'pdf', createdAt: now, attachments: [{ name: 'a.pdf', mediaType: 'application/pdf', sizeBytes: 1 }] });

    expect(await detectUnusedFeatureSteps('u1')).toEqual([]);
  });

  it("ignores another account's history", async () => {
    await db.notes.add({ id: 'n2', userId: 'someone-else', conversationId: 'c', messageId: 'm', content: 'x', createdAt: now, updatedAt: now, isPinned: false, tags: [] } as never);
    expect(await detectUnusedFeatureSteps('u1')).toContain('addNote');
  });
});
