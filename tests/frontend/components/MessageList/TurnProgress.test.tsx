import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TurnProgress } from '../../../../frontend/src/components/MessageList/TurnProgress';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';
import type { TurnProgressEntry } from '../../../../frontend/src/store/chat/types';

const renderProgress = (steps: TurnProgressEntry[], hasAttachments = false) => render(
  <UserPreferencesProvider>
    <TurnProgress steps={steps} hasAttachments={hasAttachments} />
  </UserPreferencesProvider>,
);

describe('TurnProgress', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a local first step before the backend reports anything', () => {
    renderProgress([], true);
    expect(screen.getByTestId('turn-progress-label')).toHaveTextContent('正在上傳並讀取附件');
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('names the current step with counts and only shows elapsed time once the wait is long', () => {
    const now = Date.now();
    renderProgress([
      { step: 'analyzing', startedAt: now },
      { step: 'visual_understanding', current: 2, total: 4, startedAt: now },
    ]);

    expect(screen.getByTestId('turn-progress-label')).toHaveTextContent('正在分析圖表內容');
    expect(screen.getByTestId('turn-progress-meta')).toHaveTextContent('2/4');
    expect(screen.getByTestId('turn-progress-meta')).not.toHaveTextContent('秒');

    act(() => { vi.advanceTimersByTime(5000); });
    expect(screen.getByTestId('turn-progress-meta')).toHaveTextContent('2/4 · 5 秒');
  });

  it('expands into completed steps with the active step last', () => {
    const now = Date.now();
    renderProgress([
      { step: 'analyzing', startedAt: now },
      { step: 'visual_planning', current: 3, total: 3, startedAt: now },
      { step: 'reading_documents', current: 0, total: 3, startedAt: now },
    ]);

    expect(screen.getByTestId('turn-progress-label')).toHaveTextContent('正在閱讀 3 份附件並撰寫回答');
    expect(screen.queryByTestId('turn-progress-steps')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '顯示處理步驟' }));
    const items = screen.getByTestId('turn-progress-steps').querySelectorAll('li');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('正在分析問題');
    expect(items[1]).toHaveTextContent('正在挑選附件中的關鍵圖表 3/3');
    expect(items[2]).toHaveAttribute('aria-current', 'step');
    expect(screen.getByRole('button', { name: '隱藏處理步驟' })).toHaveAttribute('aria-expanded', 'true');
  });
});
