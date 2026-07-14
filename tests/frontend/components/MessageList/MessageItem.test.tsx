import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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
      bubble: 'bubble',
      userBubble: 'userBubble',
      bubbleWrapper: 'bubbleWrapper',
      messageAttachmentList: 'messageAttachmentList',
      messageAttachmentCard: 'messageAttachmentCard',
      messageAttachmentIcon: 'messageAttachmentIcon',
      messageAttachmentDetails: 'messageAttachmentDetails',
      messageAttachmentName: 'messageAttachmentName',
      messageAttachmentMeta: 'messageAttachmentMeta',
      messageAttachmentToggleWrap: 'messageAttachmentToggleWrap',
      messageAttachmentToggle: 'messageAttachmentToggle',
      messageAttachmentToggleIcon: 'messageAttachmentToggleIcon',
      messageAttachmentToggleChevron: 'messageAttachmentToggleChevron',
      messageAttachmentToggleChevronOpen: 'messageAttachmentToggleChevronOpen',
      messageAttachmentDropdown: 'messageAttachmentDropdown',
      messageAttachmentDropdownItem: 'messageAttachmentDropdownItem',
      messageAttachmentDropdownIcon: 'messageAttachmentDropdownIcon',
      messageAttachmentDropdownName: 'messageAttachmentDropdownName',
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
    const emptyMessage = { ...baseMessage, content: '' };
    const ragInfo = {
      status: 'searching_dense' as const,
      message: '檢索中...',
      sources: [],
    };
    
    render(
      <MessageItem 
        message={emptyMessage} 
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

  it('renders persisted user attachment metadata below the message text', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '請解釋這份 PDF',
          attachments: [{ name: 'lesson.pdf', mediaType: 'application/pdf', sizeBytes: 2048 }],
        }}
      />
    );

    expect(screen.getByText('請解釋這份 PDF')).toBeInTheDocument();
    expect(screen.getByLabelText('附件 lesson.pdf')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
    expect(screen.getByLabelText('訊息附件').closest('.userBubble')).not.toBeInTheDocument();
  });

  it('hides the legacy attachment marker and renders a compatibility card', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '請解釋這份 PDF\n\n[已附加 1 個檔案]',
        }}
      />
    );

    expect(screen.queryByText(/已附加 1 個檔案/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('附件 附件 1')).toBeInTheDocument();
  });

  it('renders quote-branch attachments outside the user bubble', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '> 原始問題\n\n請解釋這份 PDF',
          attachments: [{ name: 'lesson.pdf', mediaType: 'application/pdf', sizeBytes: 2048 }],
        }}
      />
    );

    expect(screen.getByLabelText('訊息附件').closest('.userBubble')).not.toBeInTheDocument();
    expect(screen.getByText('原始問題')).toBeInTheDocument();
    expect(screen.getByText('請解釋這份 PDF')).toBeInTheDocument();
  });

  it('collapses multiple attachments into an expandable filename list', () => {
    render(
      <MessageItem
        message={{
          ...baseMessage,
          role: 'user',
          content: '請幫我確認',
          attachments: [
            { name: 'first.pdf', mediaType: 'application/pdf', sizeBytes: 2048 },
            { name: 'second.pdf', mediaType: 'application/pdf', sizeBytes: 4096 },
          ],
        }}
      />
    );

    const toggle = screen.getByRole('button', { name: /2 個附件/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('附件檔名列表')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('附件 first.pdf')).not.toBeInTheDocument();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('附件檔名列表')).toBeInTheDocument();
    expect(screen.getByText('first.pdf')).toBeInTheDocument();
    expect(screen.getByText('second.pdf')).toBeInTheDocument();
  });
});
