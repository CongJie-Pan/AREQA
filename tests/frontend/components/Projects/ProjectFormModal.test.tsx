import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { describe, expect, it, vi } from 'vitest';

import { ProjectFormModal } from '@/components/Projects';

vi.mock('@/contexts/UserPreferencesContext', () => ({
  useUserPreferences: () => ({ language: 'zh-TW', t: (key: string) => key }),
}));

function renderModal(props: Partial<React.ComponentProps<typeof ProjectFormModal>> = {}) {
  const handlers = { onClose: vi.fn(), onSubmit: vi.fn().mockResolvedValue(undefined), ...props };
  render(<App><ProjectFormModal open {...handlers} /></App>);
  return handlers;
}

describe('ProjectFormModal', () => {
  it('asks for the work and the goal, and creates only once a name is given', async () => {
    const { onSubmit, onClose } = renderModal();

    expect(screen.getByText('projectNameLabel')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('projectNamePlaceholder')).toBeInTheDocument();
    expect(screen.getByText('projectGoalLabel')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('projectGoalPlaceholder')).toBeInTheDocument();
    const create = screen.getByRole('button', { name: 'projectCreate' });
    expect(create).toBeDisabled();

    fireEvent.change(screen.getByLabelText('projectNameLabel'), { target: { value: '  Thesis  ' } });
    fireEvent.change(screen.getByLabelText('projectGoalLabel'), { target: { value: ' Finish chapter two ' } });
    fireEvent.click(create);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ name: 'Thesis', description: 'Finish chapter two' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('Enter in the name field submits; Cancel closes without saving', async () => {
    const { onSubmit, onClose } = renderModal();
    const name = screen.getByLabelText('projectNameLabel');
    fireEvent.change(name, { target: { value: 'Diary' } });
    fireEvent.submit(name.closest('form')!);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ name: 'Diary', description: '' }));

    onSubmit.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));
    expect(onClose).toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('edit mode starts from the current values and saves', async () => {
    const { onSubmit } = renderModal({ mode: 'edit', initialValues: { name: 'Diary', description: 'Daily notes' } });
    expect(screen.getByText('projectEditTitle')).toBeInTheDocument();
    expect(screen.getByLabelText('projectNameLabel')).toHaveValue('Diary');
    expect(screen.getByLabelText('projectGoalLabel')).toHaveValue('Daily notes');
    fireEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ name: 'Diary', description: 'Daily notes' }));
  });
});
