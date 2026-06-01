import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MessageItem } from '../../../../frontend/src/components/MessageList/MessageItem';

// Mock child components to isolate tests
vi.mock('../../../../frontend/src/components/RAGStatusPanel', () => ({
  RAGStatusPanel: ({ ragInfo }: any) => (
    <div data-testid="rag-status-panel">{ragInfo.message}</div>
  )
}));

vi.mock('../../../../frontend/src/components/MessageList/styles', () => ({
  useStyles: () => ({
    styles: { 
      assistantMessageWrapper: 'assistantMessageWrapper', 
      assistantBubble: 'assistantBubble',
      content: 'content',
      streamingCursor: 'streamingCursor'
    },
    cx: (...args: any[]) => args.filter(Boolean).join(' '),
  }),
}));

// Mock markdown component
vi.mock('react-markdown', () => ({
  default: ({ children }: any) => <div>{children}</div>
}));

describe('MessageItem Integration with RAGStatusPanel', () => {
  const baseMessage = {
    id: 'msg-1',
    role: 'assistant' as const,
    content: '這是測試訊息',
    createdAt: Date.now(),
  };

  it('Scenario 1: Render RAGStatusPanel when active', () => {
    const ragInfo = {
      status: 'searching_dense' as const,
      message: '檢索中...',
      sources: [],
    };
    
    render(
      <MessageItem 
        message={baseMessage} 
        isStreaming={true} 
        ragInfo={ragInfo} 
      />
    );
    
    const panel = screen.getByTestId('rag-status-panel');
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveTextContent('檢索中...');
  });

  it('Scenario 2: Do not render RAGStatusPanel when idle', () => {
    const ragInfo = {
      status: 'idle' as const,
      message: '',
      sources: [],
    };
    
    render(
      <MessageItem 
        message={baseMessage} 
        isStreaming={true} 
        ragInfo={ragInfo} 
      />
    );
    
    expect(screen.queryByTestId('rag-status-panel')).not.toBeInTheDocument();
  });
});
