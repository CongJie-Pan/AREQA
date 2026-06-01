import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SuggestedQuestions } from '@/components/SuggestedQuestions';
import React from 'react';

// Mock framer-motion to avoid animation issues in tests
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
}));

describe('SuggestedQuestions', () => {
  const mockSuggestions = ['問題1', '問題2', '問題3'];
  const mockOnSelect = vi.fn();

  it('renders correctly with suggestions', () => {
    render(
      <SuggestedQuestions 
        suggestions={mockSuggestions} 
        onSelect={mockOnSelect} 
      />
    );

    expect(screen.getByText('您可能還想了解：')).toBeInTheDocument();
    expect(screen.getByText('問題1')).toBeInTheDocument();
    expect(screen.getByText('問題2')).toBeInTheDocument();
    expect(screen.getByText('問題3')).toBeInTheDocument();
  });

  it('calls onSelect when a button is clicked', () => {
    render(
      <SuggestedQuestions 
        suggestions={mockSuggestions} 
        onSelect={mockOnSelect} 
      />
    );

    fireEvent.click(screen.getByText('問題1'));
    expect(mockOnSelect).toHaveBeenCalledWith('問題1');
  });

  it('does not render when suggestions are empty', () => {
    const { container } = render(
      <SuggestedQuestions 
        suggestions={[]} 
        onSelect={mockOnSelect} 
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('disables buttons when disabled prop is true', () => {
    render(
      <SuggestedQuestions 
        suggestions={mockSuggestions} 
        onSelect={mockOnSelect}
        disabled={true}
      />
    );

    const button = screen.getByText('問題1').closest('button');
    expect(button).toBeDisabled();
  });
});
