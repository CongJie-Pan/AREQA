import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatContainer } from '@/components/ChatContainer';
import { useChatStore } from '@/store/chat';
import { sendMessage } from '@/services/chat';

// Mock chat service
vi.mock('@/services/chat', () => ({
  sendMessage: vi.fn().mockResolvedValue(undefined),
  loadMessages: vi.fn(),
  initializeChatService: vi.fn(),
  cancelCurrentStream: vi.fn(),
  regenerateMessage: vi.fn(),
  editUserMessage: vi.fn(),
}));

// Mock selection hook to trigger it manually
vi.mock('@/hooks/useTextSelection', () => {
  let mockSetSelection = (text: string, rect: any) => {};
  return {
    useTextSelection: () => {
      const [selection, setSelection] = React.useState({ text: '', rect: null });
      // Expose setter for testing
      (window as any).triggerSelection = (text: string, rect: any) => {
        act(() => {
          setSelection({ text, rect });
        });
      };
      return {
        ...selection,
        clearSelection: () => setSelection({ text: '', rect: null }),
      };
    },
  };
});

describe('Text Selection Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Initialize store state
    useChatStore.getState().setMessages([
      { id: '1', role: 'assistant', content: '這是紅樓夢的內容。', createdAt: new Date() }
    ]);
    useChatStore.getState().setQuotedText(null);
  });

  it('should flow from selection to quoting in input', async () => {
    render(<ChatContainer />);

    // 1. Simulate selection
    (window as any).triggerSelection('紅樓夢', { top: 100, left: 100, width: 50, height: 20 });

    // 2. Verify toolbar appears with correct label
    expect(await screen.findByText('問小紅(引用)')).toBeDefined();

    // 3. Click "Ask XiaoHong" (Quote)
    fireEvent.click(screen.getByText('問小紅(引用)'));

    // 4. Verify toolbar disappears and quote appears in input
    expect(screen.queryByText('問小紅(引用)')).toBeNull();
    expect(screen.getByText('紅樓夢')).toBeDefined();

    // 5. Type question and send
    const input = screen.getByPlaceholderText(/歡迎問我問題/i);
    fireEvent.change(input, { target: { value: '這是什麼？' } });
    fireEvent.click(screen.getByLabelText(/發送訊息/i));

    // 6. Verify sendMessage called with concatenated content
    const lastCall = (sendMessage as any).mock.calls[0];
    expect(lastCall[0]).toContain('> 紅樓夢');
    expect(lastCall[0]).toContain('這是什麼？');
    
    // 7. Verify quote is cleared
    expect(screen.queryByText('紅樓夢')).toBeNull();
  });

  it('should flow from selection to explain automatically', async () => {
    render(<ChatContainer />);

    // 1. Simulate selection
    (window as any).triggerSelection('林黛玉', { top: 100, left: 100, width: 50, height: 20 });

    // 2. Click "Explain"
    fireEvent.click(await screen.findByText('幫我解釋'));

    // 3. Verify sendMessage called immediately
    const lastCall = (sendMessage as any).mock.calls[0];
    expect(lastCall[0]).toContain('請幫我解釋這段文字：');
    expect(lastCall[0]).toContain('> 林黛玉');
  });
});
