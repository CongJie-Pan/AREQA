import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SharedConversationView } from '../../../../frontend/src/app/share/[token]/SharedConversationView';

describe('SharedConversationView', () => {
  const conversation = {
    id: 'conversation-1',
    title: 'Shared table',
    createdAt: '2026-08-25T00:00:00.000Z',
    updatedAt: '2026-08-25T00:00:00.000Z',
    messages: [
      {
        id: 'message-1',
        role: 'assistant' as const,
        content: [
          '| Metric | Value |',
          '| --- | --- |',
          '| Accuracy | 98% |',
          '| Latency | 120ms |',
        ].join('\n'),
        createdAt: '2026-08-25T00:00:00.000Z',
      },
    ],
  };

  it('renders markdown tables with an expandable read-only modal', () => {
    render(<SharedConversationView conversation={conversation} />);

    expect(screen.getByRole('table')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展開表格' }));

    const dialog = screen.getByRole('dialog', { name: '展開的表格' });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole('table')).toBeInTheDocument();
    expect(within(dialog).getByText('Accuracy')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '關閉表格' }));

    expect(screen.queryByRole('dialog', { name: '展開的表格' })).not.toBeInTheDocument();
  });
});
