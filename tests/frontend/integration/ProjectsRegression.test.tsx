import 'fake-indexeddb/auto';
import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationList } from '@/components/ConversationList';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import { db } from '@/database/db';
import type { Conversation, Project } from '@/database/schema';
import { conversationRepo } from '@/database/repositories/conversationRepo';
import { projectService } from '@/services/projects';
import { useAuthStore } from '@/store/auth';
import { useConversationStore } from '@/store/conversation/store';
import { useProjectStore } from '@/store/projects';

/**
 * Regressions for behaviour that existed before projects and must not change:
 * the signed-out sidebar, collaborative copies, deleting data, and plain new chats.
 */

const USER = 'projects-regression-user';
const PROJECT_ID = '7a1c2b6e-1d2a-4c3b-9a8e-123456789abc';

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: () => ({
      upsert: async () => ({ error: null }),
      select: () => ({ eq: async () => ({ data: [], error: null }) }),
      delete: () => ({ eq: async () => ({ error: null }) }),
    }),
  },
}));
vi.mock('@/database/db', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/database/db')>(),
  getCurrentUserId: vi.fn(() => USER),
}));
vi.mock('@/services/syncService', () => ({
  syncService: new Proxy({}, { get: () => vi.fn().mockResolvedValue(true) }),
  normalizeRequestModes: () => undefined,
}));
vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt ?? ''} />,
}));
vi.mock('@/components/Auth', () => ({ UserAuthUI: () => <div /> }));
vi.mock('@/services/chat', () => ({
  switchConversation: vi.fn(async (id: string) => useConversationStore.getState().selectConversation(id)),
  logConversationHistoryDebugEvent: vi.fn(),
  deleteConversation: vi.fn(),
}));

const at = new Date('2026-11-20T00:00:00Z');
const project: Project = {
  id: PROJECT_ID, userId: USER, name: 'Diary', instructions: '', useAccountMemory: true, isPinned: true,
  memorySummary: null, memoryDetails: [], memoryUpdatedAt: null, createdAt: at, updatedAt: at,
};
function conversation(overrides: Partial<Conversation>): Conversation {
  return { id: 'c', userId: USER, title: 'Chat', createdAt: at, updatedAt: at, messageCount: 1, lastMessagePreview: '', ...overrides };
}

function renderSidebar(props: Partial<React.ComponentProps<typeof ConversationList>> = {}) {
  return render(<UserPreferencesProvider><App><ConversationList {...props} /></App></UserPreferencesProvider>);
}

describe('Projects regressions', () => {
  beforeEach(async () => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    await db.open();
    await Promise.all([db.conversations.clear(), db.messages.clear(), db.projects.clear(), db.conversationSyncQueue.clear()]);
    useAuthStore.setState({ user: { id: USER } as never });
    useProjectStore.setState({ projects: [project], view: { kind: 'list' }, draftProjectId: null, loadedUserId: USER });
    useConversationStore.setState({
      conversations: [conversation({ id: 'plain', title: 'Plain chat' })],
      activeConversationId: null, workspace: 'chat', streamingTitles: {}, isLoading: false,
    });
  });

  it('signed-out sidebar shows no Projects entry, no pinned projects and no project menu items', async () => {
    useAuthStore.setState({ user: null });
    renderSidebar();

    expect(screen.queryByRole('button', { name: '專案' })).toBeNull();
    expect(screen.queryByText('Diary')).toBeNull();
    fireEvent.click(screen.getByTitle('對話選單'));
    await screen.findByRole('menuitem', { name: /重新命名/ });
    expect(screen.queryByRole('menuitem', { name: /加入專案/ })).toBeNull();
  });

  it('collaborative copies cannot be filed into a project', async () => {
    useConversationStore.setState({ conversations: [conversation({
      id: 'shared', title: 'Shared chat', collaboration: { role: 'editor', ownerUserId: 'someone' },
    })] });
    renderSidebar();

    fireEvent.click(screen.getByTitle('對話選單'));
    await screen.findByRole('menuitem', { name: /重新命名/ });
    expect(screen.queryByRole('menuitem', { name: /加入專案/ })).toBeNull();
  });

  it('chat menu follows image 07: Pin, Rename, Add to project, …, Delete last', async () => {
    renderSidebar();
    fireEvent.click(screen.getByTitle('對話選單'));
    await screen.findByRole('menuitem', { name: /加入專案/ });
    const labels = screen.getAllByRole('menuitem').map((item) => item.textContent ?? '');
    expect(labels.slice(0, 3).map((label) => label.replace(/\s/g, ''))).toEqual(['釘選聊天', '重新命名', '加入專案']);
    expect(labels.at(-1)).toMatch(/刪除/);
  });

  it('the project row menu is named apart from chat menus', () => {
    renderSidebar();
    expect(screen.getAllByTitle('對話選單')).toHaveLength(1);
    expect(screen.getByTitle('專案選單')).toBeInTheDocument();
  });

  it('opening a chat from the sidebar while a project page is open does not file the next new chat', async () => {
    useProjectStore.getState().showProject(PROJECT_ID);
    const onSelect = vi.fn(() => useProjectStore.getState().setDraftProjectId(null));
    renderSidebar({ onSelect });

    fireEvent.click(screen.getByText('Plain chat'));
    await waitFor(() => expect(onSelect).toHaveBeenCalled());

    const created = await conversationRepo.create(undefined, 'chat', useProjectStore.getState().takeDraftProjectId());
    expect(created.projectId).toBeUndefined();
  });

  it('deleting a project keeps its conversations and their messages', async () => {
    await db.projects.put(project);
    await db.conversations.put(conversation({ id: 'inside', projectId: PROJECT_ID }));
    await db.messages.put({ id: 'm1', userId: USER, conversationId: 'inside', role: 'user', content: 'keep me', createdAt: at });

    await projectService.remove(PROJECT_ID);

    expect((await db.conversations.get('inside'))?.projectId).toBeNull();
    expect((await db.messages.get('m1'))?.content).toBe('keep me');
  });

  it('plain new conversations are still created without a project field', async () => {
    const created = await conversationRepo.create();
    expect(created).not.toHaveProperty('projectId');
    expect(await db.conversations.get(created.id)).not.toHaveProperty('projectId');
  });
});
