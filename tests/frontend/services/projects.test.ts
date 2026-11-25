import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { db, getCurrentUserId } from '@/database/db';
import { conversationRepo } from '@/database/repositories/conversationRepo';
import type { Project } from '@/database/schema';
import { projectFromCloud, projectService } from '@/services/projects';
import { syncService } from '@/services/syncService';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { useProjectStore } from '@/store/projects';

const supabaseState = vi.hoisted(() => ({
  upsert: vi.fn(),
  select: { data: [] as unknown[] | null, error: null as unknown },
  deleteEq: vi.fn(),
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: () => ({
      upsert: supabaseState.upsert,
      select: () => ({ eq: async () => supabaseState.select }),
      delete: () => ({ eq: supabaseState.deleteEq }),
    }),
  },
}));

vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: vi.fn(),
}));

vi.mock('@/services/syncService', () => ({
  syncService: { pushConversation: vi.fn(), pushMessage: vi.fn(), deleteConversation: vi.fn() },
}));

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));

const USER = 'project-owner';

function project(overrides: Partial<Project> = {}): Project {
  const at = new Date('2026-11-20T00:00:00.000Z');
  return {
    id: '7a1c2b6e-1d2a-4c3b-9a8e-123456789abc', userId: USER, name: 'Diary', instructions: '',
    useAccountMemory: true, isPinned: false, memorySummary: null, memoryDetails: [], memoryUpdatedAt: null,
    createdAt: at, updatedAt: at, ...overrides,
  };
}

function cloudRow(value: Project, overrides: Record<string, unknown> = {}) {
  return {
    id: value.id, user_id: value.userId, name: value.name, instructions: value.instructions,
    use_account_memory: value.useAccountMemory, is_pinned: value.isPinned, memory_summary: value.memorySummary,
    memory_details: value.memoryDetails, memory_updated_at: null,
    created_at: value.createdAt.toISOString(), updated_at: value.updatedAt.toISOString(), ...overrides,
  };
}

describe('projectService', () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue(USER);
    vi.mocked(syncService.pushConversation).mockResolvedValue(true);
    supabaseState.upsert.mockResolvedValue({ error: null });
    supabaseState.deleteEq.mockResolvedValue({ error: null });
    supabaseState.select = { data: [], error: null };
    await db.open();
    await Promise.all([db.projects.clear(), db.conversations.clear(), db.conversationSyncQueue.clear()]);
  });

  it('creates a project locally, pushes it, and clears the pending flag', async () => {
    const created = await projectService.create('  Diary  ');
    expect(created.name).toBe('Diary');
    await vi.waitFor(async () => expect((await db.projects.get(created.id))?.syncPending).toBe(false));
    expect(supabaseState.upsert).toHaveBeenCalledWith(expect.objectContaining({ id: created.id, name: 'Diary', user_id: USER }));
  });

  it('keeps a failed push pending and retries it on the next sync', async () => {
    supabaseState.upsert.mockResolvedValueOnce({ error: { code: '503' } });
    const created = await projectService.create('Offline');
    await vi.waitFor(() => expect(supabaseState.upsert).toHaveBeenCalledTimes(1));
    expect((await db.projects.get(created.id))?.syncPending).toBe(true);

    supabaseState.select = { data: [], error: null };
    const merged = await projectService.sync(USER);
    expect(merged.map((item) => item.id)).toEqual([created.id]);
    expect(supabaseState.upsert).toHaveBeenCalledTimes(2);
    expect((await db.projects.get(created.id))?.syncPending).toBe(false);
  });

  it('takes newer cloud rows and drops synced projects deleted elsewhere', async () => {
    const kept = project();
    const gone = project({ id: '8b1c2b6e-1d2a-4c3b-9a8e-123456789abc', name: 'Gone' });
    await db.projects.bulkPut([kept, gone]);
    await db.conversations.add({
      id: 'c1', userId: USER, title: 't', createdAt: kept.createdAt, updatedAt: kept.updatedAt,
      messageCount: 0, lastMessagePreview: '', projectId: gone.id,
    });
    supabaseState.select = { data: [cloudRow(kept, { name: 'Renamed', updated_at: '2026-11-21T00:00:00.000Z' })], error: null };

    const merged = await projectService.sync(USER);

    expect(merged.map((item) => item.name)).toEqual(['Renamed']);
    expect((await db.conversations.get('c1'))?.projectId).toBeNull();
  });

  it('removing a project keeps its conversations', async () => {
    const value = project();
    await db.projects.put(value);
    await db.conversations.add({
      id: 'c2', userId: USER, title: 't', createdAt: value.createdAt, updatedAt: value.updatedAt,
      messageCount: 0, lastMessagePreview: '', projectId: value.id,
    });

    await projectService.remove(value.id);

    expect(await db.projects.get(value.id)).toBeUndefined();
    expect((await db.conversations.get('c2'))?.projectId).toBeNull();
    expect(supabaseState.deleteEq).toHaveBeenCalledWith('id', value.id);
  });

  it('applies memory returned by the backend without marking the project pending', async () => {
    await db.projects.put(project());
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({
      memory: { summary: 'Keeps a diary', details: ['Writes nightly', 7], updated_at: '2026-11-25T00:00:00.000Z' },
    }), { status: 200 }));

    const updated = await projectService.reviseMemory(project().id, ' shorter ');

    expect(vi.mocked(authenticatedFetch).mock.calls[0][0]).toBe(`/api/projects/${project().id}/memory/revise`);
    expect(JSON.parse(String(vi.mocked(authenticatedFetch).mock.calls[0][1]?.body))).toEqual({ instruction: 'shorter' });
    expect(updated.memorySummary).toBe('Keeps a diary');
    expect(updated.memoryDetails).toEqual(['Writes nightly']);
    expect(updated.syncPending).toBeUndefined();
  });
});

describe('draft project for new conversations', () => {
  beforeEach(async () => {
    vi.mocked(getCurrentUserId).mockReturnValue(USER);
    useProjectStore.getState().reset();
    await db.open();
    await db.conversations.clear();
  });

  it('a project page hands its project to exactly one new conversation', async () => {
    useProjectStore.getState().showProject('7a1c2b6e-1d2a-4c3b-9a8e-123456789abc');

    const first = await conversationRepo.create(undefined, 'chat', useProjectStore.getState().takeDraftProjectId());
    const second = await conversationRepo.create(undefined, 'chat', useProjectStore.getState().takeDraftProjectId());

    expect(first.projectId).toBe('7a1c2b6e-1d2a-4c3b-9a8e-123456789abc');
    expect(second.projectId).toBeUndefined();
  });

  it('the project list page never assigns a project', () => {
    useProjectStore.getState().showProject('7a1c2b6e-1d2a-4c3b-9a8e-123456789abc');
    useProjectStore.getState().showList();
    expect(useProjectStore.getState().takeDraftProjectId()).toBeNull();
  });
});

describe('project goal (description)', () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    vi.mocked(getCurrentUserId).mockReturnValue(USER);
    vi.mocked(syncService.pushConversation).mockResolvedValue(true);
    supabaseState.upsert.mockResolvedValue({ error: null });
    await db.open();
    await Promise.all([db.projects.clear(), db.conversations.clear()]);
  });

  it('creates with a trimmed goal and pushes it', async () => {
    const created = await projectService.create('Thesis', '  Finish chapter two  ');
    expect(created.description).toBe('Finish chapter two');
    await vi.waitFor(() => expect(supabaseState.upsert).toHaveBeenCalledWith(
      expect.objectContaining({ id: created.id, description: 'Finish chapter two' })));
  });

  it('keeps syncing without the goal when the description column is not migrated', async () => {
    supabaseState.upsert
      .mockResolvedValueOnce({ error: { code: 'PGRST204', message: "Could not find the 'description' column of 'projects'" } })
      .mockResolvedValueOnce({ error: null });
    const created = await projectService.create('Thesis', 'Goal');

    await vi.waitFor(async () => expect((await db.projects.get(created.id))?.syncPending).toBe(false));
    expect(supabaseState.upsert.mock.calls[1][0]).not.toHaveProperty('description');
    expect((await db.projects.get(created.id))?.description).toBe('Goal');
  });

  it('older cloud rows without a goal read as empty', () => {
    const value = projectFromCloud({
      id: 'p', user_id: USER, name: 'Old', instructions: null, use_account_memory: null, is_pinned: null,
      memory_summary: null, memory_details: null, memory_updated_at: null,
      created_at: '2026-11-20T00:00:00Z', updated_at: '2026-11-20T00:00:00Z',
    });
    expect(value.description).toBe('');
  });
});
