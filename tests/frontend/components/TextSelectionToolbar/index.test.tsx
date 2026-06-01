import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { App } from 'antd';
import { TextSelectionToolbar } from '@/components/TextSelectionToolbar';
import { useTextSelection } from '@/hooks/useTextSelection';
import { useChatStore } from '@/store/chat';
import { sendMessage } from '@/services/chat';

// 1. Mock only our custom hooks and domain logic services
vi.mock('@/hooks/useTextSelection', () => ({
  useTextSelection: vi.fn(),
}));

vi.mock('@/store/chat', () => ({
  useChatStore: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  sendMessage: vi.fn(),
}));

// Mock useStyles to avoid theme complexity in unit tests
vi.mock('./styles', () => ({
  useStyles: () => ({
    styles: {
      toolbar: 'toolbar',
      button: 'button',
      label: 'label',
      divider: 'divider',
    },
    cx: (...args: any[]) => args.filter(Boolean).join(' '),
  }),
}));

describe('TextSelectionToolbar (Integration with AntD)', () => {
  const mockClearSelection = vi.fn();
  const mockSetQuotedText = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock selection state
    (useTextSelection as any).mockReturnValue({
      text: 'selected text',
      rect: { top: 100, left: 100, width: 50, height: 20 } as DOMRect,
      clearSelection: mockClearSelection,
    });

    // Mock store state
    (useChatStore as any).mockImplementation((selector: any) => {
      if (typeof selector === 'function') {
        return selector({ setQuotedText: mockSetQuotedText });
      }
      return { setQuotedText: mockSetQuotedText };
    });

    // Mock clipboard API
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
      configurable: true,
      writable: true,
    });
  });

  /**
   * Helper to render with AntD App context
   */
  const renderWithContext = (ui: React.ReactElement) => {
    return render(
      <App>
        {ui}
      </App>
    );
  };

  it('should not render when no text is selected', () => {
    (useTextSelection as any).mockReturnValue({
      text: '',
      rect: null,
      clearSelection: mockClearSelection,
    });
    
    const { container } = renderWithContext(<TextSelectionToolbar />);
    expect(container.querySelector('.selection-toolbar')).toBeNull();
  });

  it('should render when text is selected', () => {
    renderWithContext(<TextSelectionToolbar />);
    expect(screen.getByRole('button', { name: /複製/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /問小紅/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /幫我解釋/i })).toBeDefined();
  });

  it('should call clipboard and show success message on copy', async () => {
    renderWithContext(<TextSelectionToolbar />);
    const copyBtn = screen.getByRole('button', { name: /複製/i });
    
    fireEvent.click(copyBtn);
    
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('selected text');
    });

    // Check if AntD success message appears in the DOM
    expect(await screen.findByText('已複製到剪貼簿')).toBeInTheDocument();
    expect(mockClearSelection).toHaveBeenCalled();
  });

  it('should call setQuotedText on quote click', () => {
    renderWithContext(<TextSelectionToolbar />);
    const quoteBtn = screen.getByRole('button', { name: /問小紅/i });
    
    fireEvent.click(quoteBtn);
    
    expect(mockSetQuotedText).toHaveBeenCalledWith('selected text');
    expect(mockClearSelection).toHaveBeenCalled();
  });

  it('should call sendMessage on explain click', async () => {
    renderWithContext(<TextSelectionToolbar />);
    const explainBtn = screen.getByRole('button', { name: /幫我解釋/i });
    
    fireEvent.click(explainBtn);
    
    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith(expect.stringContaining('請幫我解釋這段文字'));
    });
    
    expect(sendMessage).toHaveBeenCalledWith(expect.stringContaining('selected text'));
    expect(mockClearSelection).toHaveBeenCalled();
  });

  it('should show error message if clipboard write fails', async () => {
    (navigator.clipboard.writeText as any).mockRejectedValueOnce(new Error('Copy failed'));
    
    renderWithContext(<TextSelectionToolbar />);
    const copyBtn = screen.getByRole('button', { name: /複製/i });
    
    fireEvent.click(copyBtn);
    
    // Check if AntD error message appears in the DOM
    expect(await screen.findByText('複製失敗')).toBeInTheDocument();
    expect(mockClearSelection).not.toHaveBeenCalled();
  });
});
