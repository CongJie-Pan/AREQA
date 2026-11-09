import { StrictMode, createElement, type ReactNode } from 'react';
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStreamingReveal } from '@/components/MessageList/useStreamingReveal';

vi.mock('@/utils/logger', () => ({ logger: { debug: vi.fn() } }));
const originalMatchMedia = window.matchMedia;
beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); window.matchMedia = originalMatchMedia; vi.useRealTimers(); });

describe('shared streaming display cursor', () => {
  it('continues revealing after StrictMode replays effect setup and cleanup', () => {
    const { result, unmount } = renderHook(() => useStreamingReveal('嚴格模式也要正常呈現', true), {
      wrapper: ({ children }: { children: ReactNode }) => createElement(StrictMode, null, children),
    });
    act(() => vi.advanceTimersByTime(64));
    expect(result.current.content.length).toBeGreaterThan(0);
    expect(result.current.content.length).toBeLessThan('嚴格模式也要正常呈現'.length);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps a combining mark attached when it arrives in a later packet', () => {
    const { result, rerender } = renderHook(({ content }) => useStreamingReveal(content, true), {
      initialProps: { content: 'e' },
    });
    act(() => vi.advanceTimersByTime(32));
    rerender({ content: 'e\u0301續' });
    act(() => vi.advanceTimersByTime(32));
    expect(result.current.content).toBe('e\u0301續');
  });

  it('continues forward when packets arrive and releases each paragraph in source order', () => {
    const { result, rerender } = renderHook(({ content, receiving }) => useStreamingReveal(content, receiving), {
      initialProps: { content: '甲'.repeat(60), receiving: true },
    });
    act(() => vi.advanceTimersByTime(64));
    const prefix = result.current.content;
    expect(prefix.length).toBeGreaterThan(0);
    rerender({ content: `${'甲'.repeat(60)}\n\n${'乙'.repeat(60)}`, receiving: true });
    expect(result.current.content).toBe(prefix);
    act(() => vi.advanceTimersByTime(32));
    expect(result.current.content.startsWith(prefix)).toBe(true);
    expect(result.current.content).not.toContain('乙');
  });

  it('smoothly drains a large final packet and releases its timer', () => {
    const { result, rerender, unmount } = renderHook(({ content, receiving }) => useStreamingReveal(content, receiving), {
      initialProps: { content: 'start', receiving: true },
    });
    act(() => vi.advanceTimersByTime(32));
    const prefix = result.current.content;
    const content = `start${'end'.repeat(1000)}`;
    rerender({ content, receiving: false });
    expect(result.current.content).toBe(prefix);
    expect(result.current.isRevealing).toBe(true);
    act(() => vi.advanceTimersByTime(512));
    expect(result.current.content).toBe(content);
    expect(result.current.isRevealing).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('preserves emoji, combining marks and grapheme boundaries', () => {
    const { result } = renderHook(() => useStreamingReveal('👨‍👩‍👧‍👦e\u0301😀中尾', true));
    act(() => vi.advanceTimersByTime(32));
    expect(result.current.content).toBe('👨‍👩‍👧‍👦e\u0301');
  });

  it('shows historical messages, voice-owned text and completed edits immediately', () => {
    const { result, rerender } = renderHook(({ content, receiving, disabled }) => useStreamingReveal(content, receiving, disabled), {
      initialProps: { content: 'history', receiving: false, disabled: false },
    });
    expect(result.current.content).toBe('history');
    expect(result.current.animate).toBe(false);
    rerender({ content: 'voice', receiving: true, disabled: true });
    expect(result.current.content).toBe('voice');
    expect(vi.getTimerCount()).toBe(0);
    rerender({ content: 'live', receiving: true, disabled: false });
    act(() => vi.advanceTimersByTime(100));
    rerender({ content: 'live', receiving: false, disabled: false });
    act(() => vi.advanceTimersByTime(512));
    rerender({ content: 'live edited', receiving: false, disabled: false });
    expect(result.current.content).toBe('live edited');
    expect(result.current.animate).toBe(false);
  });

  it('bypasses both pacing and animation when reduced motion is requested', () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const { result } = renderHook(() => useStreamingReveal('完整內容', true));
    expect(result.current.content).toBe('完整內容');
    expect(result.current.animate).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('cleans up an unfinished response on unmount and never invents text after cancellation', () => {
    const { result, rerender, unmount } = renderHook(({ receiving }) => useStreamingReveal('已收到的文字', receiving), {
      initialProps: { receiving: true },
    });
    act(() => vi.advanceTimersByTime(32));
    rerender({ receiving: false });
    act(() => vi.advanceTimersByTime(512));
    expect(result.current.content).toBe('已收到的文字');
    rerender({ receiving: true });
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
