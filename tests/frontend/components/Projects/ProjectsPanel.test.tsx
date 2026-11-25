import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectsPanel } from '@/components/Projects';
import { useProjectStore } from '@/store/projects';
import { useConversationStore } from '@/store/conversation';
import type { Conversation, Project } from '@/database/schema';

vi.mock('@/components/ChatInput', () => ({
  ChatInput: ({ onSend, placeholder }: { onSend: (text: string) => void; placeholder?: string }) => (
    <button type="button" onClick={() => onSend('hello')}>{placeholder}</button>
  ),
}));

vi.mock('@/contexts/UserPreferencesContext', () => ({
  useUserPreferences: () => ({
    language: 'en',
    t: (key: string, params?: Record<string, string>) => (params?.name ? `${key}:${params.name}` : key),
  }),
}));

const PROJECT_ID = '7a1c2b6e-1d2a-4c3b-9a8e-123456789abc';
const at = new Date('2026-11-20T00:00:00.000Z');

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: PROJECT_ID, userId: 'u', name: 'Diary', instructions: 'Answer briefly.', useAccountMemory: true,
    isPinned: false, memorySummary: 'Keeps a nightly diary', memoryDetails: ['Lives in a dorm'],
    memoryUpdatedAt: at, createdAt: at, updatedAt: at, ...overrides,
  };
}

function conversation(overrides: Partial<Conversation>): Conversation {
  return { id: 'c', userId: 'u', title: 'Chat', createdAt: at, updatedAt: at, messageCount: 1, lastMessagePreview: '', ...overrides };
}

function renderPanel(props: Partial<React.ComponentProps<typeof ProjectsPanel>> = {}) {
  const handlers = { onStartChat: vi.fn(), onOpenConversation: vi.fn(), onOpenAccountMemory: vi.fn(), ...props };
  render(<App><ProjectsPanel {...handlers} /></App>);
  return handlers;
}

describe('ProjectsPanel', () => {
  beforeEach(() => {
    useProjectStore.setState({ projects: [project()], view: { kind: 'project', projectId: PROJECT_ID }, draftProjectId: PROJECT_ID });
    useConversationStore.setState({ conversations: [
      conversation({ id: 'in', title: 'Friendship reflections', projectId: PROJECT_ID }),
      conversation({ id: 'out', title: 'Unrelated chat' }),
    ] });
  });

  it('lists only the project chats and starts a new chat from its composer', () => {
    const handlers = renderPanel();

    expect(screen.getByText('Friendship reflections')).toBeInTheDocument();
    expect(screen.queryByText('Unrelated chat')).toBeNull();
    fireEvent.click(screen.getByText('Friendship reflections'));
    expect(handlers.onOpenConversation).toHaveBeenCalledWith('in');

    fireEvent.click(screen.getByRole('button', { name: 'projectNewSession:Diary' }));
    expect(handlers.onStartChat).toHaveBeenCalledWith('hello');
  });

  it('shows the memory profile and toggles account memory', async () => {
    const update = vi.fn().mockResolvedValue(project({ useAccountMemory: false }));
    useProjectStore.setState({ update });
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: 'projectView' }));
    expect(await screen.findByText('Keeps a nightly diary')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('switch', { name: 'projectUseAccountMemory' }));
    expect(update).toHaveBeenCalledWith(PROJECT_ID, { useAccountMemory: false });

    fireEvent.click(screen.getByRole('button', { name: /projectMemoryProfile/ }));
    expect(await screen.findByText('Lives in a dorm')).toBeInTheDocument();
  });

  it('shows the list page with pinned projects first', () => {
    useProjectStore.setState({
      view: { kind: 'list' },
      projects: [project({ id: 'a', name: 'Alpha' }), project({ id: 'b', name: 'Beta', isPinned: true })],
    });
    renderPanel();
    const names = screen.getAllByText(/Alpha|Beta/).map((node) => node.textContent);
    expect(names).toEqual(['Beta', 'Alpha']);
  });
});

describe('isProjectMemoryStale', () => {
  it('refreshes when memory is missing or older than newer chats, but not too often', async () => {
    const { isProjectMemoryStale } = await import('@/components/Projects/ProjectMemoryModal');
    const now = Date.parse('2026-11-25T12:00:00Z');
    expect(isProjectMemoryStale(null, null, now)).toBe(false);
    expect(isProjectMemoryStale(null, now, now)).toBe(true);
    expect(isProjectMemoryStale(new Date('2026-11-25T08:00:00Z'), Date.parse('2026-11-25T09:00:00Z'), now)).toBe(true);
    expect(isProjectMemoryStale(new Date('2026-11-25T11:30:00Z'), Date.parse('2026-11-25T11:45:00Z'), now)).toBe(false);
    expect(isProjectMemoryStale(new Date('2026-11-25T08:00:00Z'), Date.parse('2026-11-25T07:00:00Z'), now)).toBe(false);
  });
});
