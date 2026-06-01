import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatInput } from '@/components/ChatInput';
import { useChatStore } from '@/store/chat';

// Mock Zustand store
vi.mock('@/store/chat', () => ({
  useChatStore: vi.fn(),
}));

describe('ChatInput', () => {
  const mockOnSend = vi.fn();
  const mockSetQuotedText = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Default store mock
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        useRag: false,
        forceThink: false,
        quotedText: null,
        toggleRag: vi.fn(),
        toggleThink: vi.fn(),
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });
  });

  it('should render correctly', () => {
    render(<ChatInput onSend={mockOnSend} />);
    expect(screen.getByPlaceholderText(/問我任何問題/i)).toBeDefined();
  });

  it('should show quote preview when quotedText is provided', () => {
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        quotedText: 'this is a quote',
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    render(<ChatInput onSend={mockOnSend} />);
    expect(screen.getByText('this is a quote')).toBeDefined();
    expect(screen.getByLabelText(/取消引用/i)).toBeDefined();
  });

  it('should call setQuotedText(null) when close button is clicked', () => {
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        quotedText: 'this is a quote',
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    render(<ChatInput onSend={mockOnSend} />);
    const closeBtn = screen.getByLabelText(/取消引用/i);
    fireEvent.click(closeBtn);
    
    expect(mockSetQuotedText).toHaveBeenCalledWith(null);
  });

  it('should merge quote into message when sending', () => {
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        quotedText: 'quoted content',
        setQuotedText: mockSetQuotedText,
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByPlaceholderText(/問我任何問題/i);
    
    fireEvent.change(input, { target: { value: 'my question' } });
    fireEvent.click(screen.getByLabelText(/發送訊息/i));
    
    expect(mockOnSend).toHaveBeenCalledWith(expect.stringContaining('> quoted content'));
    expect(mockOnSend).toHaveBeenCalledWith(expect.stringContaining('my question'));
    expect(mockSetQuotedText).toHaveBeenCalledWith(null);
  });
});
