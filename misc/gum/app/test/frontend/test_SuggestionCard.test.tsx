import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SuggestionCard from '../../frontEnd/src/components/SuggestionCard';
import { useStore } from '../../frontEnd/src/store/useStore';

describe('SuggestionCard Component', () => {
  const mockSuggestion = {
    id: 's1',
    title: 'Automate tasks',
    description: 'Use a script',
    benefit: 8,
    confidence: 9
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('renders suggestion details', () => {
    render(<SuggestionCard suggestion={mockSuggestion} />);
    expect(screen.getByText('Automate tasks')).toBeInTheDocument();
    expect(screen.getByText('Use a script')).toBeInTheDocument();
    expect(screen.getByText('Benefit: 8/10')).toBeInTheDocument();
  });

  it('shows executing state when run is clicked', async () => {
    vi.useFakeTimers();
    render(<SuggestionCard suggestion={mockSuggestion} />);
    
    const runBtn = screen.getByText('Start Chat / Run');
    fireEvent.click(runBtn);
    
    expect(screen.getByText('Executing...')).toBeInTheDocument();
    
    vi.advanceTimersByTime(3000);
    vi.useRealTimers();
    
    await waitFor(() => {
      expect(screen.getByText('Action Completed')).toBeInTheDocument();
    });
  });

  it('calls submitFeedback when liked', async () => {
    const submitFeedbackMock = vi.fn().mockResolvedValue(true);
    useStore.setState({ submitFeedback: submitFeedbackMock });
    
    render(<SuggestionCard suggestion={mockSuggestion} />);
    const likeBtn = screen.getByTitle('Helpful');
    fireEvent.click(likeBtn);
    
    await waitFor(() => {
      expect(submitFeedbackMock).toHaveBeenCalledWith('s1', true);
    });
  });

  it('shows feedback textarea when disliked and submits text', async () => {
    const submitFeedbackMock = vi.fn().mockResolvedValue(true);
    useStore.setState({ submitFeedback: submitFeedbackMock });
    
    render(<SuggestionCard suggestion={mockSuggestion} />);
    const dislikeBtn = screen.getByTitle('Not helpful');
    fireEvent.click(dislikeBtn);
    
    // Textarea should appear
    const textarea = screen.getByPlaceholderText("Tell Gumbo why this isn't helpful...");
    expect(textarea).toBeInTheDocument();
    
    fireEvent.change(textarea, { target: { value: 'Too generic' } });
    
    const submitBtn = screen.getByText('Submit');
    fireEvent.click(submitBtn);
    
    await waitFor(() => {
      expect(submitFeedbackMock).toHaveBeenCalledWith('s1', false, 'Too generic');
    });
  });
});
