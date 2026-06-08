import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MemoryTable from '../../frontEnd/src/components/MemoryTable';
import { useStore } from '../../frontEnd/src/store/useStore';

describe('MemoryTable Component', () => {
  beforeEach(() => {
    // Reset vi mocks
    vi.clearAllMocks();
  });

  it('renders empty state when no propositions exist', () => {
    render(<MemoryTable propositions={[]} />);
    expect(screen.getByText('No Propositions Logged')).toBeInTheDocument();
  });

  it('renders propositions correctly', () => {
    const props = [
      { id: 1, text: 'Likes coffee', reasoning: 'Drinks it every day', confidence: 9, created_at: 'now' }
    ];
    render(<MemoryTable propositions={props} />);
    expect(screen.getByText('Likes coffee')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
  });

  it('enters edit mode and calls updateMemory', async () => {
    const updateMemoryMock = vi.fn().mockResolvedValue(true);
    useStore.setState({ updateMemory: updateMemoryMock });

    const props = [
      { id: 1, text: 'Likes coffee', reasoning: 'Drinks it every day', confidence: 9, created_at: 'now' }
    ];
    render(<MemoryTable propositions={props} />);
    
    // Click Edit
    const editBtn = screen.getByTitle('Edit');
    fireEvent.click(editBtn);

    // Change text
    const input = screen.getByDisplayValue('Likes coffee');
    fireEvent.change(input, { target: { value: 'Loves coffee' } });

    // Save
    const saveBtn = screen.getByTitle('Save');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(updateMemoryMock).toHaveBeenCalledWith(1, 'Loves coffee', 9);
    });
  });

  it('calls deleteMemory when delete is clicked and confirmed', async () => {
    const deleteMemoryMock = vi.fn().mockResolvedValue(true);
    useStore.setState({ deleteMemory: deleteMemoryMock });
    vi.spyOn(window, 'confirm').mockImplementation(() => true);

    const props = [
      { id: 1, text: 'Likes coffee', reasoning: 'Drinks it every day', confidence: 9, created_at: 'now' }
    ];
    render(<MemoryTable propositions={props} />);
    
    // Click Delete
    const deleteBtn = screen.getByTitle('Delete');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(deleteMemoryMock).toHaveBeenCalledWith(1);
    });
  });
});
