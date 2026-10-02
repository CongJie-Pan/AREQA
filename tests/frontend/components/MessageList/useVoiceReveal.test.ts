import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useVoiceReveal } from '@/components/MessageList/useVoiceReveal';

afterEach(() => vi.useRealTimers());

describe('voice caption playback', () => {
  it('catches up a finished transcript and leaves historical text immediate', () => {
    vi.useFakeTimers();
    const { result, rerender, unmount } = renderHook(({ state }) => useVoiceReveal('這是完整語音回覆', state), {
      initialProps: { state: 'finished' as 'finished' | undefined },
    });
    expect(result.current).toBe('這是完整語音回覆');
    rerender({ state: undefined });
    expect(result.current).toBe('這是完整語音回覆');
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('stops revealing unheard text on interruption', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ state }) => useVoiceReveal('第一段接著第二段', state), {
      initialProps: { state: 'playing' as 'playing' | 'interrupted' },
    });
    act(() => vi.advanceTimersByTime(200));
    expect(result.current).toBe('第');
    rerender({ state: 'interrupted' });
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current).toBe('第');
  });
});

it('does not reveal captions until playback starts, even after a long wait', () => {
  vi.useFakeTimers();
  const { result, rerender } = renderHook(({ state }) => useVoiceReveal('尚未播放的文字', state), {
    initialProps: { state: 'waiting' as 'waiting' | 'playing' },
  });
  act(() => vi.advanceTimersByTime(10_000));
  expect(result.current).toBe('');
  rerender({ state: 'playing' });
  act(() => vi.advanceTimersByTime(200));
  expect(result.current).toBe('尚');
});

it('shows only sentences released by playback while retaining the complete answer', () => {
  const { result, rerender } = renderHook(({ caption }) => useVoiceReveal('First. Second.', 'playing', caption), {
    initialProps: { caption: '' },
  });
  expect(result.current).toBe('');
  rerender({ caption: 'First.' });
  expect(result.current).toBe('First.');
});
