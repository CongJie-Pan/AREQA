import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectInstructionsModal } from '@/components/Projects';
import type { Project } from '@/database/schema';
import { useProjectStore } from '@/store/projects';

vi.mock('@/contexts/UserPreferencesContext', () => ({
  useUserPreferences: () => ({
    language: 'zh-TW',
    t: (key: string, params?: Record<string, string>) => (params?.name ? `${key}:${params.name}` : key),
  }),
}));

const at = new Date('2026-11-25T00:00:00Z');
const project: Project = {
  id: 'p1', userId: 'u', name: 'Diary', description: '', instructions: 'Be brief.', useAccountMemory: true,
  isPinned: false, memorySummary: null, memoryDetails: [], memoryUpdatedAt: null, createdAt: at, updatedAt: at,
};

describe('ProjectInstructionsModal', () => {
  const update = vi.fn();
  beforeEach(() => {
    update.mockReset().mockResolvedValue(project);
    useProjectStore.setState({ update });
  });

  function renderModal(onClose = vi.fn()) {
    render(<App><ProjectInstructionsModal project={project} open onClose={onClose} /></App>);
    return onClose;
  }

  it('shows the title, the project-specific intro and the placeholder, with no close icon', () => {
    renderModal();
    expect(screen.getByText('projectInstructionsTitle')).toBeInTheDocument();
    expect(screen.getByText('projectInstructionsIntro:Diary')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('projectInstructionsPlaceholder')).toHaveValue('Be brief.');
    expect(screen.queryByRole('button', { name: /close/i })).toBeNull();
  });

  it('keeps Save disabled until the text changes, then saves trimmed text and closes', async () => {
    const onClose = renderModal();
    const save = screen.getByRole('button', { name: 'projectInstructionsSave' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText('projectInstructions'), { target: { value: '  Use examples.  ' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(update).toHaveBeenCalledWith('p1', { instructions: 'Use examples.' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('Cancel closes without saving', () => {
    const onClose = renderModal();
    fireEvent.change(screen.getByLabelText('projectInstructions'), { target: { value: 'changed' } });
    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));
    expect(onClose).toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
  });
});
