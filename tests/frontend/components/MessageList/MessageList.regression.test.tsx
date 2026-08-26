import React from 'react';
import { act, render, fireEvent, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
      empty: 'empty',
      emptyLogo: 'emptyLogo',
      emptyCopy: 'emptyCopy',
      emptySubtitle: 'emptySubtitle',
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

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the reduced-motion empty state with the circular AREQA icon', () => {
    (window.matchMedia as any).mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [],
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

    const { container } = render(<MessageList />);
    const logo = screen.getByAltText('AREQA Logo');

    expect(logo).toHaveAttribute('src', expect.stringContaining('areqa_icon_v4_circle.png'));
    expect(container.querySelector('.emptyCopy')).toBeInTheDocument();
    expect(screen.getByLabelText('嗨! 我是 AREQA👋，你最好的學習夥伴。😊🌸')).toHaveTextContent(
      '嗨! 我是 AREQA👋，你最好的學習夥伴。😊🌸',
    );
    expect(screen.queryByLabelText('今天想學什麼呢？🤔')).not.toBeInTheDocument();
  });

  it('types, pauses, deletes, and rotates empty-state copy', async () => {
    vi.useFakeTimers();
    (window.matchMedia as any).mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [],
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

    render(<MessageList />);

    const firstLine = '嗨! 我是 AREQA👋，你最好的學習夥伴。😊🌸';
    const secondLine = '今天想學什麼呢？🤔';

    expect(screen.getByLabelText(firstLine)).toHaveTextContent('');

    for (let step = 0; step < 140; step += 1) {
      await act(async () => {
        vi.advanceTimersToNextTimer();
      });

      const secondLineElement = screen.queryByLabelText(secondLine);
      if (secondLineElement?.textContent === secondLine) {
        break;
      }
    }

    expect(screen.getByLabelText(secondLine)).toHaveTextContent(secondLine);
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
