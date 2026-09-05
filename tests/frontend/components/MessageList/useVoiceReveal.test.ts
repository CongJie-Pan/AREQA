import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useVoiceReveal } from '@/components/MessageList/useVoiceReveal';

afterEach(() => vi.useRealTimers());

describe('voice caption playback', () => {
  it('reveals a done-only transcript gradually and leaves historical text immediate', () => {
    vi.useFakeTimers();
    const { result, rerender, unmount } = renderHook(({ state }) => useVoiceReveal('這是完整語音回覆', state), {
      initialProps: { state: 'finished' as 'finished' | undefined },
    });
    expect(result.current).toBe('');
    act(() => vi.advanceTimersByTime(130));
    expect(result.current).toBe('這');
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
    act(() => vi.advanceTimersByTime(130));
    expect(result.current).toBe('第');
    rerender({ state: 'interrupted' });
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current).toBe('第');
  });
});
