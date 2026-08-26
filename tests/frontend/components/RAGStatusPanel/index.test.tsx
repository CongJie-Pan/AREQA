import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RAGStatusPanel } from '../../../../frontend/src/components/RAGStatusPanel';
import type { RAGInfo } from '../../../../frontend/src/components/RAGStatusPanel';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';

vi.mock('../../../../frontend/src/components/RAGStatusPanel/styles', () => ({
  useStyles: () => ({
    styles: {
      container: 'container',
      header: 'header',
      statusInfo: 'statusInfo',
      radarWrapper: 'radarWrapper',
      radarCore: 'radarCore',
      radarRing: 'radarRing',
      checkIcon: 'checkIcon',
      spinnerWrapper: 'spinnerWrapper',
      routingIcon: 'routingIcon',
      statusText: 'statusText',
      sourceCount: 'sourceCount',
    },
    cx: (...args: string[]) => args.filter(Boolean).join(' '),
  }),
}));

describe('RAGStatusPanel', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('shows frontend-owned routing progress text in an accessible live region', () => {
    render(
      <RAGStatusPanel
        ragInfo={{ status: 'routing', message: 'Backend should not own UI copy', sources: [] }}
      />,
    );

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('正在分析問題')).toBeInTheDocument();
    expect(screen.queryByText('Backend should not own UI copy')).not.toBeInTheDocument();
  });

  it('uses the selected interface language for visible pipeline text', () => {
    window.localStorage.setItem('areqa:interface-language', 'en');

    render(
      <UserPreferencesProvider>
        <RAGStatusPanel
          ragInfo={{ status: 'searching_dense', message: 'Backend dense-search text', sources: [] }}
        />
      </UserPreferencesProvider>,
    );

    expect(screen.getByText('Searching related sources')).toBeInTheDocument();
    expect(screen.queryByText('Backend dense-search text')).not.toBeInTheDocument();
  });

  it('returns null for idle state', () => {
    const ragInfo: RAGInfo = { status: 'idle', message: '', sources: [] };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);

    expect(container.firstChild).toBeNull();
  });

  it('shows radar animation for visible retrieval search state', () => {
    const ragInfo: RAGInfo = {
      status: 'searching_dense',
      message: 'Backend dense-search text',
      sources: [],
    };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);

    expect(screen.getByText('正在搜尋相關文獻')).toBeInTheDocument();
    expect(screen.queryByText('Backend dense-search text')).not.toBeInTheDocument();
    expect(container.querySelector('.radarWrapper')).toBeInTheDocument();
    expect(container.querySelector('.radarCore')).toBeInTheDocument();
    expect(container.querySelector('.radarRing')).toBeInTheDocument();
  });

  it.each([
    'retrieving',
    'searching_sparse',
    'reranking',
    'sources_ready',
    'generating',
  ] as const)('does not render frontend panel for backend-only status %s', (status) => {
    const ragInfo: RAGInfo = {
      status,
      message: `Backend-only ${status}`,
      sources: Array(5).fill({ title: 'Mock Source', snippet: 'text', score: 1, chunk_id: '1' }),
    };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByText(`Backend-only ${status}`)).not.toBeInTheDocument();
  });
});
