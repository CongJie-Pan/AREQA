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

const mockSources = Array(5).fill({
  title: 'Mock Source',
  snippet: 'text',
  score: 1,
  chunk_id: '1',
});

describe('RAGStatusPanel', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it.each([
    'idle',
    'routing',
    'retrieving',
    'searching_dense',
    'searching_sparse',
    'reranking',
    'sources_ready',
    'generating',
    'done',
  ] as const)('does not render generic pipeline status %s without RAG sources', (status) => {
    const ragInfo: RAGInfo = {
      status,
      message: `Backend-only ${status}`,
      sources: [],
    };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByText(`Backend-only ${status}`)).not.toBeInTheDocument();
  });

  it('renders only when RAG source evidence is available', () => {
    render(
      <RAGStatusPanel
        ragInfo={{
          status: 'sources_ready',
          message: 'Backend should not own UI copy',
          sources: mockSources,
        }}
      />,
    );

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('已完成文獻檢索')).toBeInTheDocument();
    expect(screen.getByText('找到 5 筆文獻')).toBeInTheDocument();
    expect(screen.queryByText('Backend should not own UI copy')).not.toBeInTheDocument();
  });

  it('uses the selected interface language for RAG source evidence', () => {
    window.localStorage.setItem('areqa:interface-language', 'en');

    render(
      <UserPreferencesProvider>
        <RAGStatusPanel
          ragInfo={{
            status: 'sources_ready',
            message: 'Backend should not own UI copy',
            sources: mockSources,
          }}
        />
      </UserPreferencesProvider>,
    );

    expect(screen.getByText('Source retrieval complete')).toBeInTheDocument();
    expect(screen.getByText('Found 5 sources')).toBeInTheDocument();
    expect(screen.queryByText('Backend should not own UI copy')).not.toBeInTheDocument();
  });
});
