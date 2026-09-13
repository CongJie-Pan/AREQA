import React from 'react';
import { act, render, fireEvent, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MessageList } from '../../../../frontend/src/components/MessageList';
import { useChatStore } from '../../../../frontend/src/store/chat';
import { useConversationStore } from '../../../../frontend/src/store/conversation';
import { requestSourceMessageFocus } from '../../../../frontend/src/utils/messageFocus';

// Mock store
vi.mock('../../../../frontend/src/store/chat', () => ({
  useChatStore: vi.fn(),
  chatSelectors: {
    displayMessages: (state: any) => state.messages,
  }
}));

vi.mock('../../../../frontend/src/store/conversation', () => ({
  useConversationStore: vi.fn(),
}));

// Mock styles
vi.mock('../../../../frontend/src/components/MessageList/styles', () => ({
  useStyles: () => ({
    styles: { 
      viewport: 'viewport',
      container: 'container',
      nonEmpty: 'nonEmpty',
      empty: 'empty',
      emptyLogoStage: 'emptyLogoStage',
      emptyLogo: 'emptyLogo',
      emptyCopy: 'emptyCopy',
      emptySubtitle: 'emptySubtitle',
      scrollButtonSpacer: 'scrollButtonSpacer',
      scrollButton: 'scrollButton',
      sourceFocusedMessage: 'sourceFocusedMessage'
    },
    cx: (...args: any[]) => args.filter(Boolean).join(' '),
  }),
}));

// Mock MessageItem
vi.mock('../../../../frontend/src/components/MessageList/MessageItem', () => ({
  MessageItem: ({ message, className }: any) => (
    <div data-testid="message-item" data-message-id={message.id} className={className}>
      {message.content}
    </div>
  )
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
    vi.stubGlobal('cancelAnimationFrame', vi.fn());

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

    (useConversationStore as any).mockImplementation((selector: any) => {
      const state = { activeConversationId: 'conversation-1', isLoading: false, isMessageHandoffLoading: false };
      return typeof selector === 'function' ? selector(state) : state;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    window.sessionStorage.clear();
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
    expect(container.querySelector('.areqa-message-empty-logo-stage')).toBeInTheDocument();
    expect(container.querySelector('.emptyCopy')).toBeInTheDocument();
    expect(screen.getByLabelText('嗨! 我是 AREQA👋，你最好的學習夥伴。😊🌸')).toHaveTextContent(
      '嗨! 我是 AREQA👋，你最好的學習夥伴。😊🌸',
    );
    expect(screen.queryByLabelText('今天想學什麼呢？🤔')).not.toBeInTheDocument();
  });

  it('does not flash the new-chat empty state while a saved conversation is loading', () => {
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
    (useConversationStore as any).mockImplementation((selector: any) => {
      const state = { isLoading: false, isMessageHandoffLoading: true };
      return typeof selector === 'function' ? selector(state) : state;
    });

    const { container } = render(<MessageList />);

    expect(container.querySelector('.areqa-message-list-non-empty')).toBeInTheDocument();
    expect(container.querySelector('.areqa-message-list-empty')).not.toBeInTheDocument();
    expect(screen.queryByAltText('AREQA Logo')).not.toBeInTheDocument();
  });

  it('keeps the new-chat empty state visible while only the conversation list is loading', () => {
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
    (useConversationStore as any).mockImplementation((selector: any) => {
      const state = { isLoading: true, isMessageHandoffLoading: false };
      return typeof selector === 'function' ? selector(state) : state;
    });

    const { container } = render(<MessageList />);

    expect(container.querySelector('.areqa-message-list-empty')).toBeInTheDocument();
    expect(screen.getByAltText('AREQA Logo')).toBeInTheDocument();
  });

  it('reserves mobile top space for fixed chat action controls when messages exist', () => {
    const { container } = render(<MessageList />);

    expect(container.querySelector('.container')).toHaveClass('nonEmpty');
    expect(container.querySelector('.areqa-message-list-non-empty')).toBeInTheDocument();
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

  it('should not snap back during streaming after a small manual drag near the bottom', async () => {
    const { container, rerender } = render(<MessageList />);
    const scrollContainer = container.querySelector('.container') as HTMLDivElement;

    // distance=20 is near enough that the previous auto-scroll heuristic
    // treated it as bottom-following, even though the user had manually moved.
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 680, configurable: true });
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true });

    fireEvent.scroll(scrollContainer);
    mockScrollTo.mockClear();

    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [{ id: '1', role: 'assistant', content: 'streaming answer update' }],
        isStreaming: true,
        currentStreamingId: '1',
        thinkingContent: 'new token',
        isThinking: false,
        ragStatus: 'done',
        ragMessage: '',
        ragSources: [],
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    rerender(<MessageList />);

    expect(mockScrollTo).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '滑動到底部' })).toBeInTheDocument();
  });

  it('should pause auto-scroll as soon as the user starts wheel scrolling during streaming', async () => {
    const { container, rerender } = render(<MessageList />);
    const scrollContainer = container.querySelector('.container') as HTMLDivElement;

    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 700, configurable: true });
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true });

    fireEvent.wheel(scrollContainer);
    mockScrollTo.mockClear();

    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [{ id: '1', role: 'assistant', content: 'streaming answer update' }],
        isStreaming: true,
        currentStreamingId: '1',
        thinkingContent: 'new token while the user is scrolling',
        isThinking: false,
        ragStatus: 'done',
        ragMessage: '',
        ragSources: [],
      };
      return typeof selector === 'function' ? selector(state) : state;
    });

    rerender(<MessageList />);

    expect(mockScrollTo).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '滑動到底部' })).toBeInTheDocument();
  });

  it('shows an overlay scroll-to-bottom button after the user scrolls up', async () => {
    const { container } = render(<MessageList />);
    const scrollContainer = container.querySelector('.container') as HTMLDivElement;

    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 500, configurable: true });
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true });

    fireEvent.scroll(scrollContainer);

    const scrollButton = screen.getByRole('button', { name: '滑動到底部' });
    expect(container.querySelector('.areqa-message-list-viewport')).toBeInTheDocument();
    expect(scrollButton).toHaveClass('areqa-message-scroll-button');

    mockScrollTo.mockClear();
    fireEvent.click(scrollButton);

    expect(mockScrollTo).toHaveBeenCalledWith(expect.objectContaining({
      top: 1000,
      behavior: 'smooth',
    }));
    expect(screen.queryByRole('button', { name: '滑動到底部' })).not.toBeInTheDocument();
  });

  it('reserves non-live bottom space so the scroll button remains above the composer', () => {
    const { container } = render(<MessageList />);

    expect(container.querySelector('.areqa-message-scroll-spacer')).toHaveClass('scrollButtonSpacer');
  });

  it('keeps the larger live voice spacer when live voice is active', () => {
    const { container } = render(<MessageList liveVoice />);

    expect(container.querySelector('.areqa-message-scroll-spacer')).not.toBeInTheDocument();
    expect(container.querySelector('.scrollButtonSpacer')).not.toBeInTheDocument();
  });

  it('opens a pending note source at the exact message and leaves a bottom button available', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    const animationFrames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      animationFrames.push(callback);
      return animationFrames.length;
    });

    (useChatStore as any).mockImplementation((selector: any) => {
      const state = {
        messages: [
          { id: 'message-user', role: 'user', content: 'question' },
          { id: 'message-source', role: 'assistant', content: 'saved answer' },
          { id: 'message-latest', role: 'assistant', content: 'latest answer' },
        ],
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

    requestSourceMessageFocus('conversation-1', 'message-source');

    const { container } = render(<MessageList />);
    const scrollContainer = container.querySelector('.container') as HTMLDivElement;
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1400, configurable: true });
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 200, configurable: true });
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 500, configurable: true });

    act(() => {
      animationFrames.forEach((callback) => callback(0));
    });

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
    expect(container.querySelector('[data-message-id="message-source"]')).toHaveClass('sourceFocusedMessage');
    expect(screen.getByRole('button', { name: '滑動到底部' })).toBeInTheDocument();
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
