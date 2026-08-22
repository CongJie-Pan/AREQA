import { App } from 'antd';
import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it } from 'vitest';

import { MessageItem } from '@/components/MessageList/MessageItem';
import type { DisplayMessage } from '@/store/chat';

function assistantMessage(answerBlocks: DisplayMessage['answerBlocks']): DisplayMessage {
  return {
    id: 'message-1',
    userId: 'user-1',
    conversationId: 'conversation-1',
    role: 'assistant',
    content: 'Fallback answer',
    answerBlocks,
    createdAt: new Date('2026-08-08T00:00:00.000Z'),
  };
}

function renderMessage(message: DisplayMessage) {
  return render(
    <App>
      <MessageItem message={message} />
    </App>,
  );
}

describe('MessageItem visual answer rendering', () => {
  it('renders answer blocks in backend-provided order', () => {
    const { container } = renderMessage(
      assistantMessage([
        {
          type: 'paragraph',
          text: '第一段。',
        },
        {
          type: 'paragraph',
          text: '第二段。',
        },
      ]),
    );

    const blocks = Array.from(container.querySelectorAll('[data-answer-block-index]'));

    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toHaveAttribute('data-answer-block-index', '0');
    expect(blocks[1]).toHaveAttribute('data-answer-block-index', '1');
  });

  it('keeps a stable skeleton slot for pending image blocks', () => {
    renderMessage(
      assistantMessage([
        {
          type: 'image_block',
          slotId: 'img-1',
          topic: 'Forest plot',
          purpose: 'chart',
          imageUrl: '',
          sourceUrl: 'https://example.edu/forest-plot',
          sourceDomain: 'example.edu',
          caption: 'Forest plot',
          status: 'pending',
          safetyStatus: 'pass',
          matchConfidence: 0,
        },
      ]),
    );

    expect(screen.getByLabelText('圖片載入中')).toBeInTheDocument();
    expect(screen.getByTestId('answer-image-skeleton')).toBeInTheDocument();
  });

  it('crossfades resolved image blocks after the browser loads the image', () => {
    renderMessage(
      assistantMessage([
        {
          type: 'paragraph',
          text: '森林圖可以呈現單一研究與合併估計。',
        },
        {
          type: 'image_block',
          slotId: 'img-1',
          topic: 'Forest plot',
          purpose: 'chart',
          imageUrl: 'https://example.edu/forest-plot.png',
          thumbnailUrl: 'https://example.edu/forest-plot-thumb.png',
          sourceUrl: 'https://example.edu/forest-plot',
          sourceDomain: 'example.edu',
          caption: 'Forest plot example',
          explanatoryCaption: '這張圖用來說明效果量與信賴區間。',
          status: 'resolved',
          safetyStatus: 'pass',
          matchConfidence: 0.92,
          width: 1200,
          height: 700,
        },
      ]),
    );

    const image = screen.getByAltText('Forest plot example');
    expect(screen.getByText('森林圖可以呈現單一研究與合併估計。')).toBeInTheDocument();
    expect(screen.getByTestId('answer-image-skeleton')).toBeInTheDocument();

    fireEvent.load(image);

    expect(screen.queryByTestId('answer-image-skeleton')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /來源/i })).toHaveAttribute(
      'href',
      'https://example.edu/forest-plot',
    );
  });
});
