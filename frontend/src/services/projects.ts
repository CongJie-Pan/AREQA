/**
 * Projects: local IndexedDB cache plus Supabase sync, and the project-memory API.
 *
 * Writes land locally first and are pushed right away. A push that fails keeps
 * `syncPending` so the next load retries it; cloud rows never overwrite a
 * pending local row. Every Supabase failure is soft: projects keep working
 * locally. Logs carry ids and error codes only, never names, instructions or
 * memory text.
 */
import { db, getCurrentUserId } from '@/database/db';
import type { Conversation, Project } from '@/database/schema';
import { supabase } from '@/lib/supabase';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { syncService } from '@/services/syncService';
import { generateUUID } from '@/utils/id';
import { logger } from '@/utils/logger';

export const MAX_PROJECT_NAME_CHARS = 120;
export const MAX_PROJECT_INSTRUCTIONS_CHARS = 8000;

type CloudProjectRow = {
  id: string;
  user_id: string;
  name: string;
  instructions: string | null;
  use_account_memory: boolean | null;
  is_pinned: boolean | null;
  memory_summary: string | null;
  memory_details: unknown;
  memory_updated_at: string | null;
  created_at: string;
  updated_at: string;
};

export interface ProjectMemoryView {
  summary: string | null;
  details: string[];
  updated_at: string | null;
}

/** Fields the learner can change directly; memory changes go through the memory helpers. */
export type ProjectPatch = Partial<Pick<Project, 'name' | 'instructions' | 'useAccountMemory' | 'isPinned'>>;

function cleanDetails(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((item): item is string => typeof item === 'string' && item.trim() !== '') : [];
}

export function projectFromCloud(row: CloudProjectRow): Project {
  return {
    id: row.id,
    userId: row.user_id,
    name: row.name,
    instructions: row.instructions ?? '',
    useAccountMemory: row.use_account_memory !== false,
    isPinned: row.is_pinned === true,
    memorySummary: row.memory_summary ?? null,
    memoryDetails: cleanDetails(row.memory_details),
    memoryUpdatedAt: row.memory_updated_at ? new Date(row.memory_updated_at) : null,
    createdAt: new Date(row.created_at),
    updatedAt: new Date(row.updated_at),
  };
}

function projectToCloud(project: Project): CloudProjectRow {
  return {
    id: project.id,
    user_id: project.userId,
    name: project.name,
    instructions: project.instructions,
    use_account_memory: project.useAccountMemory,
    is_pinned: project.isPinned,
    memory_summary: project.memorySummary,
    memory_details: project.memoryDetails,
    memory_updated_at: project.memoryUpdatedAt?.toISOString() ?? null,
    created_at: project.createdAt.toISOString(),
    updated_at: project.updatedAt.toISOString(),
  };
}

function errorCode(error: unknown): string {
  if (error && typeof error === 'object' && 'code' in error) return String((error as { code?: unknown }).code);
  return error instanceof Error ? error.name : 'UnknownError';
}

function requireUserId(): string {
  const userId = getCurrentUserId();
  if (!userId) throw new Error('Authentication required to use projects');
  return userId;
}

/**
 * Push one project; on success clear its pending flag and re-push conversation
 * links that were deferred because the project row did not exist in the cloud yet.
 */
async function pushProject(project: Project): Promise<boolean> {
  const { error } = await supabase.from('projects').upsert(projectToCloud(project));
  if (error) {
    logger.warn('project_push_failed', { component: 'projects', projectId: project.id, code: errorCode(error) });
    return false;
  }
  const current = await db.projects.get(project.id);
  if (current && current.updatedAt.getTime() === project.updatedAt.getTime()) {
    await db.projects.update(project.id, { syncPending: false });
  }
  const linked = await db.conversations.where('projectId').equals(project.id).toArray();
  await Promise.all(linked.map((conversation: Conversation) => syncService.pushConversation(conversation)));
  return true;
}

async function saveLocal(project: Project): Promise<Project> {
  const pending = { ...project, syncPending: true };
  await db.projects.put(pending);
  void pushProject(pending);
  return pending;
}

export const projectService = {
  /** Local projects for the user, newest first. */
  async listLocal(userId: string): Promise<Project[]> {
    const rows = await db.projects.where('userId').equals(userId).toArray();
    return rows.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
  },

  /**
   * Merge cloud rows into the local cache and retry pending pushes.
   * Returns the merged list, or the local list when the cloud is unavailable.
   */
  async sync(userId: string): Promise<Project[]> {
    const local = await db.projects.where('userId').equals(userId).toArray();
    const { data, error } = await supabase.from('projects').select('*').eq('user_id', userId);
    if (error || !Array.isArray(data)) {
      logger.warn('project_pull_failed', { component: 'projects', code: errorCode(error) });
      return this.listLocal(userId);
    }
    const cloud = new Map((data as CloudProjectRow[]).map((row) => [row.id, projectFromCloud(row)]));
    const localById = new Map(local.map((project) => [project.id, project]));
    const toPut: Project[] = [];
    const toDelete: string[] = [];
    for (const [id, remote] of cloud) {
      const mine = localById.get(id);
      if (mine?.syncPending) continue;
      if (!mine || mine.updatedAt.getTime() < remote.updatedAt.getTime()
        || (mine.memoryUpdatedAt?.getTime() ?? 0) !== (remote.memoryUpdatedAt?.getTime() ?? 0)) {
        toPut.push(remote);
      }
    }
    // A synced local project missing from the cloud was deleted on another device.
    for (const project of local) {
      if (!cloud.has(project.id) && !project.syncPending) toDelete.push(project.id);
    }
    await db.transaction('rw', [db.projects, db.conversations], async () => {
      if (toPut.length) await db.projects.bulkPut(toPut);
      for (const id of toDelete) {
        await db.projects.delete(id);
        await db.conversations.where('projectId').equals(id).modify({ projectId: null });
      }
    });
    const pending = local.filter((project) => project.syncPending);
    await Promise.all(pending.map((project) => pushProject(project)));
    logger.info('project_sync_finished', {
      component: 'projects', cloudCount: cloud.size, updated: toPut.length, removed: toDelete.length, retried: pending.length,
    });
    return this.listLocal(userId);
  },

  async create(name: string): Promise<Project> {
    const userId = requireUserId();
    const now = new Date();
    const project: Project = {
      id: generateUUID(),
      userId,
      name: name.trim().slice(0, MAX_PROJECT_NAME_CHARS),
      instructions: '',
      useAccountMemory: true,
      isPinned: false,
      memorySummary: null,
      memoryDetails: [],
      memoryUpdatedAt: null,
      createdAt: now,
      updatedAt: now,
    };
    logger.info('project_created', { component: 'projects', projectId: project.id });
    return saveLocal(project);
  },

  async update(id: string, patch: ProjectPatch): Promise<Project> {
    const current = await db.projects.get(id);
    if (!current) throw new Error('Project not found');
    const next: Project = {
      ...current,
      ...patch,
      ...(patch.name !== undefined ? { name: patch.name.trim().slice(0, MAX_PROJECT_NAME_CHARS) } : {}),
      ...(patch.instructions !== undefined
        ? { instructions: patch.instructions.slice(0, MAX_PROJECT_INSTRUCTIONS_CHARS) } : {}),
      updatedAt: new Date(),
    };
    return saveLocal(next);
  },

  /** Delete the project; its conversations stay and simply leave the project. */
  async remove(id: string): Promise<void> {
    await db.transaction('rw', [db.projects, db.conversations], async () => {
      await db.projects.delete(id);
      await db.conversations.where('projectId').equals(id).modify({ projectId: null });
    });
    const { error } = await supabase.from('projects').delete().eq('id', id);
    if (error) logger.warn('project_delete_failed', { component: 'projects', projectId: id, code: errorCode(error) });
    else logger.info('project_deleted', { component: 'projects', projectId: id });
  },

  async clearMemory(id: string): Promise<Project> {
    const current = await db.projects.get(id);
    if (!current) throw new Error('Project not found');
    return saveLocal({ ...current, memorySummary: null, memoryDetails: [], memoryUpdatedAt: null, updatedAt: new Date() });
  },

  /** Rebuild memory from the project's conversations (backend reads them with the caller's JWT). */
  async refreshMemory(id: string): Promise<{ project: Project; refreshed: boolean }> {
    const payload = await callMemoryApi(id, 'refresh');
    return { project: await applyMemory(id, payload.memory), refreshed: payload.refreshed !== false };
  },

  /** Ask the backend to rewrite the memory profile following the learner's instruction. */
  async reviseMemory(id: string, instruction: string): Promise<Project> {
    const payload = await callMemoryApi(id, 'revise', { instruction: instruction.trim().slice(0, 1000) });
    return applyMemory(id, payload.memory);
  },
};

async function callMemoryApi(
  id: string, action: 'refresh' | 'revise', body?: Record<string, unknown>,
): Promise<{ memory: ProjectMemoryView; refreshed?: boolean }> {
  const current = await db.projects.get(id);
  // The backend reads the cloud row, so an unsynced project must reach Supabase first.
  if (current?.syncPending && !(await pushProject(current))) throw new Error('Project not synced');
  const response = await authenticatedFetch(`/api/projects/${encodeURIComponent(id)}/memory/${action}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    logger.warn('project_memory_request_failed', { component: 'projects', projectId: id, action, status: response.status });
    throw new Error(`Project memory ${action} failed`);
  }
  return response.json();
}

async function applyMemory(id: string, memory: ProjectMemoryView): Promise<Project> {
  const current = await db.projects.get(id);
  if (!current) throw new Error('Project not found');
  // The backend already saved this memory in the cloud, so the local copy is not pending.
  const next: Project = {
    ...current,
    memorySummary: memory.summary,
    memoryDetails: cleanDetails(memory.details),
    memoryUpdatedAt: memory.updated_at ? new Date(memory.updated_at) : null,
  };
  await db.projects.put(next);
  return next;
}
