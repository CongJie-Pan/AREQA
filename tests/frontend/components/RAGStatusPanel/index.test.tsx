import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RAGStatusPanel } from '../../../../frontend/src/components/RAGStatusPanel';
import type { RAGInfo } from '../../../../frontend/src/components/RAGStatusPanel';

// Mock the CSS module
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
      statusText: 'statusText',
      sourceCount: 'sourceCount',
    },
    cx: (...args: any[]) => args.filter(Boolean).join(' '),
  }),
}));

describe('RAGStatusPanel', () => {
  it('Scenario 1: Idle state - returns null', () => {
    const ragInfo: RAGInfo = { status: 'idle', message: '', sources: [] };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);
    expect(container.firstChild).toBeNull();
  });

  it('Scenario 2: Searching/Retrieving - shows radar animation', () => {
    const ragInfo: RAGInfo = {
      status: 'searching_dense',
      message: '📖 翻閱古籍索引...',
      sources: [],
    };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);
    
    expect(screen.getByText('📖 翻閱古籍索引...')).toBeInTheDocument();
    
    // Check for radar animation elements
    expect(container.querySelector('.radarWrapper')).toBeInTheDocument();
    expect(container.querySelector('.radarCore')).toBeInTheDocument();
    expect(container.querySelector('.radarRing')).toBeInTheDocument();
  });

  it('Scenario 3: Complete/Generating - shows check icon and sources', () => {
    const ragInfo: RAGInfo = {
      status: 'sources_ready',
      message: '已找到 5 筆文獻',
      sources: Array(5).fill({ title: 'Mock Source', snippet: 'text', score: 1, chunk_id: '1' }),
    };
    const { container } = render(<RAGStatusPanel ragInfo={ragInfo} />);
    
    expect(screen.getByText('已找到 5 筆文獻')).toBeInTheDocument();
    expect(screen.getByText('找到 5 筆文獻')).toBeInTheDocument();
    
    // Radar should be gone, replaced by completion indicator (checkIcon)
    expect(container.querySelector('.radarWrapper')).not.toBeInTheDocument();
  });
});
