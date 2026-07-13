import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
    expect(screen.getByLabelText('加入附件')).toBeInTheDocument();
    expect(screen.queryByText('0/4000')).not.toBeInTheDocument();
    const input = screen.getByLabelText('訊息輸入框');
    const attachmentButton = screen.getByLabelText('加入附件');
    expect(input.compareDocumentPosition(attachmentButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('should render a LaTeX preview without changing the submitted source', async () => {
    render(<ChatInput onSend={mockOnSend} />);
    const input = screen.getByPlaceholderText(/問我任何問題/i);

    fireEvent.change(input, { target: { value: '$$x^2 + y^2 = z^2$$' } });

    expect(await screen.findByLabelText('LaTeX 預覽')).toBeInTheDocument();
    expect(screen.getByLabelText('LaTeX 預覽').querySelector('.katex')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/發送訊息/i));
    expect(mockOnSend).toHaveBeenCalledWith('$$x^2 + y^2 = z^2$$');
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

  it('should merge quote into message when sending', async () => {
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
    await waitFor(() => expect(mockSetQuotedText).toHaveBeenCalledWith(null));
  });

  it('should send selected attachments with an otherwise empty message', () => {
    const attachment = new File(['notes'], 'notes.md', { type: 'text/markdown' });
    render(<ChatInput onSend={mockOnSend} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    expect(screen.getByLabelText('待送附件')).toBeInTheDocument();
    expect(screen.getByTitle('notes.md')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    expect(mockOnSend).toHaveBeenCalledWith('', [attachment]);
  });

  it('should remove a pending attachment before sending', () => {
    const attachment = new File(['notes'], 'notes.txt', { type: 'text/plain' });
    render(<ChatInput onSend={mockOnSend} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByLabelText('移除附件 notes.txt'));

    expect(screen.queryByLabelText('待送附件')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/發送訊息/i)).toBeDisabled();
  });

  it('should preserve attachments when sending fails', async () => {
    const attachment = new File(['notes'], 'notes.txt', { type: 'text/plain' });
    const failedSend = vi.fn().mockRejectedValue(new Error('network failure'));
    render(<ChatInput onSend={failedSend} />);

    fireEvent.change(screen.getByLabelText('選擇附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    await waitFor(() => expect(failedSend).toHaveBeenCalledWith('', [attachment]));
    expect(screen.getByLabelText('待送附件')).toBeInTheDocument();
  });
});
