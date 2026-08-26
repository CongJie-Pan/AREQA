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

  it('uses the selected interface language for pipeline text', () => {
    window.localStorage.setItem('areqa:interface-language', 'en');

    render(
      <UserPreferencesProvider>
        <RAGStatusPanel
          ragInfo={{ status: 'reranking', message: 'Backend reranking text', sources: [] }}
        />
      </UserPreferencesProvider>,
    );

    expect(screen.getByText('Ranking the most relevant material')).toBeInTheDocument();
    expect(screen.queryByText('Backend reranking text')).not.toBeInTheDocument();
  });

  it('returns null for idle state', () => {
    const ragInfo: RAGInfo = { status: 'idle', message: '', sources: [] };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);

    expect(container.firstChild).toBeNull();
  });

  it('shows radar animation for active retrieval', () => {
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

  it('shows completion icon and localized source count', () => {
    const ragInfo: RAGInfo = {
      status: 'sources_ready',
      message: 'Backend sources-ready text',
      sources: Array(5).fill({ title: 'Mock Source', snippet: 'text', score: 1, chunk_id: '1' }),
    };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);

    expect(screen.getByText('已完成文獻檢索')).toBeInTheDocument();
    expect(screen.getByText('找到 5 筆文獻')).toBeInTheDocument();
    expect(screen.queryByText('Backend sources-ready text')).not.toBeInTheDocument();
    expect(container.querySelector('.radarWrapper')).not.toBeInTheDocument();
  });
});
