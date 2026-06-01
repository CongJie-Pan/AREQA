import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MessageList } from '../../../../frontend/src/components/MessageList';
import { useChatStore } from '../../../../frontend/src/store/chat';

// Mock store
vi.mock('../../../../frontend/src/store/chat', () => ({
  useChatStore: vi.fn(),
  chatSelectors: {
    displayMessages: (state: any) => state.messages,
  }
}));

// Mock styles
vi.mock('../../../../frontend/src/components/MessageList/styles', () => ({
  useStyles: () => ({
    styles: { 
      container: 'container',
      scrollButton: 'scrollButton'
    },
    cx: (...args: any[]) => args.filter(Boolean).join(' '),
  }),
}));

// Mock MessageItem
vi.mock('../../../../frontend/src/components/MessageList/MessageItem', () => ({
  MessageItem: () => <div data-testid="message-item" />
}));

describe('MessageList Scroll Behavior Regression', () => {
  const mockScrollTo = vi.fn();
  
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock Element.prototype.scrollTo
    Element.prototype.scrollTo = mockScrollTo;
    
    // Mock requestAnimationFrame to execute immediately
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0);
      return 0;
    });

    // Default mock state
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [{ id: '1', role: 'user', content: 'hello' }],
        isStreaming: false,
        currentStreamingId: null,
        thinkingContent: '',
        isThinking: false,
        ragStatus: 'idle',
        ragMessage: '',
        ragSources: [],
      };
      return typeof selector === 'function' ? selector(state) : state;
    });
  });

  it('should scroll to bottom when new messages arrive and user is at bottom', async () => {
    const { rerender } = render(<MessageList />);
    
    // Clear initial render scrolls
    mockScrollTo.mockClear();

    // Simulate new message and streaming
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [
          { id: '1', role: 'user', content: 'hello' },
          { id: '2', role: 'assistant', content: 'hi' }
        ],
        isStreaming: true,
        currentStreamingId: '2',
        thinkingContent: '',
        isThinking: false,
        ragStatus: 'done',
        ragMessage: '',
        ragSources: [],
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    rerender(<MessageList />);
    
    // Should trigger scroll to bottom
    expect(mockScrollTo).toHaveBeenCalledWith(expect.objectContaining({
      top: expect.any(Number),
    }));
  });

  it('should pause auto-scroll when user manually scrolls up', async () => {
    const { container, rerender } = render(<MessageList />);
    const scrollContainer = container.querySelector('.container') as HTMLDivElement;
    
    // Mock scroll dimensions to simulate "NOT at bottom"
    // scrollHeight=1000, scrollTop=500, clientHeight=300 -> distance=200 (> SCROLL_THRESHOLD=30)
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 500, configurable: true });
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true });

    // Trigger scroll event to simulate manual scroll up
    fireEvent.scroll(scrollContainer);
    
    // Clear previous scrolls
    mockScrollTo.mockClear();

    // Update thinking content (streaming)
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [{ id: '1', role: 'user', content: 'hello' }],
        isStreaming: true,
        currentStreamingId: '1',
        thinkingContent: 'still thinking...',
        isThinking: true,
        ragStatus: 'idle',
        ragMessage: '',
        ragSources: [],
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    rerender(<MessageList />);
    
    // Should NOT trigger scroll to bottom because userScrolledUpRef.current is now true
    expect(mockScrollTo).not.toHaveBeenCalled();
  });

  it('should resume auto-scroll when user scrolls back to the bottom', async () => {
    const { container, rerender } = render(<MessageList />);
    const scrollContainer = container.querySelector('.container') as HTMLDivElement;
    
    // 1. First scroll up
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 500, configurable: true });
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true });
    fireEvent.scroll(scrollContainer);
    
    mockScrollTo.mockClear();

    // 2. Now scroll back to bottom (distance < 10px buffer)
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 695, configurable: true }); // distance = 5
    fireEvent.scroll(scrollContainer);

    // 3. Update thinking content
    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [{ id: '1', role: 'user', content: 'hello' }],
        isStreaming: true,
        currentStreamingId: '1',
        thinkingContent: 'resuming auto-scroll...',
        isThinking: true,
        ragStatus: 'idle',
        ragMessage: '',
        ragSources: [],
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    rerender(<MessageList />);
    
    // Should trigger scroll to bottom again
    expect(mockScrollTo).toHaveBeenCalled();
  });
});
