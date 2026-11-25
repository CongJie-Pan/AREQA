import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '@/database/schema';
import { projectService } from '@/services/projects';
import { useProjectStore } from '@/store/projects';

vi.mock('@/services/projects', () => ({
  projectService: {
    listLocal: vi.fn(), sync: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
    clearMemory: vi.fn(), refreshMemory: vi.fn(), reviseMemory: vi.fn(),
  },
}));

const at = (day: number) => new Date(`2026-11-${String(day).padStart(2, '0')}T00:00:00Z`);
function project(id: string, day: number, overrides: Partial<Project> = {}): Project {
  return {
    id, userId: 'u', name: id, instructions: '', useAccountMemory: true, isPinned: false,
    memorySummary: null, memoryDetails: [], memoryUpdatedAt: null, createdAt: at(day), updatedAt: at(day), ...overrides,
  };
}

describe('useProjectStore', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useProjectStore.getState().reset();
  });

  it('paints local projects first, then the cloud merge', async () => {
    let finishSync!: (value: Project[]) => void;
    vi.mocked(projectService.listLocal).mockResolvedValue([project('local', 1)]);
    vi.mocked(projectService.sync).mockReturnValue(new Promise((resolve) => { finishSync = resolve; }));

    const loading = useProjectStore.getState().load('u');
    await vi.waitFor(() => expect(useProjectStore.getState().projects.map((p) => p.id)).toEqual(['local']));
    finishSync([project('local', 1), project('cloud', 2)]);
    await loading;

    expect(useProjectStore.getState().projects.map((p) => p.id)).toEqual(['local', 'cloud']);
    expect(useProjectStore.getState().loadedUserId).toBe('u');
  });

  it('ignores a cloud merge that finishes after another account loaded', async () => {
    let finishSync!: (value: Project[]) => void;
    vi.mocked(projectService.listLocal).mockResolvedValueOnce([project('mine', 1)]).mockResolvedValueOnce([]);
    vi.mocked(projectService.sync)
      .mockReturnValueOnce(new Promise((resolve) => { finishSync = resolve; }))
      .mockResolvedValueOnce([]);

    const first = useProjectStore.getState().load('u');
    await vi.waitFor(() => expect(useProjectStore.getState().loadedUserId).toBe('u'));
    await useProjectStore.getState().load('other');
    finishSync([project('mine', 1)]);
    await first;

    expect(useProjectStore.getState().projects).toEqual([]);
  });

  it('keeps the list newest first after an update', async () => {
    useProjectStore.setState({ projects: [project('b', 2), project('a', 1)] });
    vi.mocked(projectService.update).mockResolvedValue(project('a', 3, { name: 'renamed' }));

    await useProjectStore.getState().update('a', { name: 'renamed' });

    expect(useProjectStore.getState().projects.map((p) => p.name)).toEqual(['renamed', 'b']);
  });

  it('removing the open project returns to the list and drops its draft', async () => {
    useProjectStore.setState({ projects: [project('a', 1)] });
    useProjectStore.getState().showProject('a');
    vi.mocked(projectService.remove).mockResolvedValue();

    await useProjectStore.getState().remove('a');

    expect(useProjectStore.getState().view).toEqual({ kind: 'list' });
    expect(useProjectStore.getState().draftProjectId).toBeNull();
    expect(useProjectStore.getState().projects).toEqual([]);
  });

  it('reports whether a memory refresh changed anything', async () => {
    useProjectStore.setState({ projects: [project('a', 1)] });
    vi.mocked(projectService.refreshMemory).mockResolvedValue({ project: project('a', 1), refreshed: false });
    await expect(useProjectStore.getState().refreshMemory('a')).resolves.toBe(false);
  });

  it('a draft is taken once', () => {
    useProjectStore.getState().setDraftProjectId('a');
    expect(useProjectStore.getState().takeDraftProjectId()).toBe('a');
    expect(useProjectStore.getState().takeDraftProjectId()).toBeNull();
  });
});
