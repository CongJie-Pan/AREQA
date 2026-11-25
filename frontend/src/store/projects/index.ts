/**
 * Projects Store
 * Project list, the project page being shown, and the project a new chat joins.
 */

import { create } from 'zustand';
import type { Project } from '@/database/schema';
import { projectService, type ProjectPatch } from '@/services/projects';
import { logger } from '@/utils/logger';

/** What the Projects panel shows: the list page, or one project's page. */
export type ProjectView = { kind: 'list' } | { kind: 'project'; projectId: string };

interface ProjectsState {
  projects: Project[];
  loadedUserId: string | null;
  view: ProjectView;
  /**
   * Project the next new conversation joins. Set while a project page is open
   * and consumed by the first send, so later "new chat" clicks start plain chats.
   */
  draftProjectId: string | null;
  load: (userId: string) => Promise<void>;
  reset: () => void;
  create: (name: string) => Promise<Project>;
  update: (id: string, patch: ProjectPatch) => Promise<Project>;
  remove: (id: string) => Promise<void>;
  clearMemory: (id: string) => Promise<Project>;
  refreshMemory: (id: string) => Promise<boolean>;
  reviseMemory: (id: string, instruction: string) => Promise<Project>;
  showList: () => void;
  showProject: (projectId: string) => void;
  setDraftProjectId: (projectId: string | null) => void;
  /** Return and clear the draft project (used once when a conversation is created). */
  takeDraftProjectId: () => string | null;
}

function replaceProject(projects: Project[], next: Project): Project[] {
  const others = projects.filter((project) => project.id !== next.id);
  return [next, ...others].sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
}

export const useProjectStore = create<ProjectsState>((set, get) => ({
  projects: [],
  loadedUserId: null,
  view: { kind: 'list' },
  draftProjectId: null,

  load: async (userId) => {
    // Local rows paint first; the cloud merge follows and never blocks the UI.
    const local = await projectService.listLocal(userId);
    set({ projects: local, loadedUserId: userId });
    try {
      const merged = await projectService.sync(userId);
      if (get().loadedUserId === userId) set({ projects: merged });
    } catch (error) {
      logger.warn('project_store_sync_failed', { reason: error instanceof Error ? error.name : 'UnknownError' });
    }
  },

  reset: () => set({ projects: [], loadedUserId: null, view: { kind: 'list' }, draftProjectId: null }),

  create: async (name) => {
    const project = await projectService.create(name);
    set((state) => ({ projects: replaceProject(state.projects, project) }));
    return project;
  },

  update: async (id, patch) => {
    const project = await projectService.update(id, patch);
    set((state) => ({ projects: replaceProject(state.projects, project) }));
    return project;
  },

  remove: async (id) => {
    await projectService.remove(id);
    set((state) => ({
      projects: state.projects.filter((project) => project.id !== id),
      view: state.view.kind === 'project' && state.view.projectId === id ? { kind: 'list' } : state.view,
      draftProjectId: state.draftProjectId === id ? null : state.draftProjectId,
    }));
  },

  clearMemory: async (id) => {
    const project = await projectService.clearMemory(id);
    set((state) => ({ projects: replaceProject(state.projects, project) }));
    return project;
  },

  refreshMemory: async (id) => {
    const { project, refreshed } = await projectService.refreshMemory(id);
    set((state) => ({ projects: replaceProject(state.projects, project) }));
    return refreshed;
  },

  reviseMemory: async (id, instruction) => {
    const project = await projectService.reviseMemory(id, instruction);
    set((state) => ({ projects: replaceProject(state.projects, project) }));
    return project;
  },

  showList: () => set({ view: { kind: 'list' }, draftProjectId: null }),
  showProject: (projectId) => set({ view: { kind: 'project', projectId }, draftProjectId: projectId }),
  setDraftProjectId: (projectId) => set({ draftProjectId: projectId }),
  takeDraftProjectId: () => {
    const projectId = get().draftProjectId;
    if (projectId) set({ draftProjectId: null });
    return projectId;
  },
}));
