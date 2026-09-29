import React from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ImageGenerationLoading } from '@/components/MessageList/ImageGenerationLoading';

describe('ImageGenerationLoading', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('reserves a visible preview and announces the current preparation stage', () => {
    render(<ImageGenerationLoading caption="正在整理參考附件…" />);
    expect(screen.getByRole('status', { name: '圖片產生中' })).toHaveStyle({ aspectRatio: '16 / 9' });
    expect(screen.getByText('正在整理參考附件…')).toBeInTheDocument();
    expect(screen.getByTestId('answer-image-skeleton')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByText('你可以隨時停止生成。')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('reassures the user after a long wait and cleans up the timer', () => {
    vi.useFakeTimers();
    const { unmount } = render(<ImageGenerationLoading caption="正在產生圖片…" />);
    act(() => vi.advanceTimersByTime(20_000));
    expect(screen.getByText('仍在生成中，請稍候…')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not claim that a completed image URL renewal is cancellable generation', () => {
    render(<ImageGenerationLoading caption="正在載入圖片…" canStop={false} frameStyle={{ aspectRatio: '1 / 1' }} />);
    expect(screen.getByRole('status')).toHaveStyle({ aspectRatio: '1 / 1' });
    expect(screen.queryByText('你可以隨時停止生成。')).not.toBeInTheDocument();
  });
});
