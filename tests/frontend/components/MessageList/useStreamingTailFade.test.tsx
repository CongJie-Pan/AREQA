import React, { useRef } from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useStreamingTailFade } from '@/components/MessageList/useStreamingTailFade';

const originalAnimate = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'animate');
afterEach(() => {
  cleanup();
  if (originalAnimate) Object.defineProperty(HTMLElement.prototype, 'animate', originalAnimate);
  else Reflect.deleteProperty(HTMLElement.prototype, 'animate');
});

function Harness({ text, strong = false, active = true }: { text: string; strong?: boolean; active?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useStreamingTailFade(ref, active);
  const spans = Array.from(text, (character, index) => <span data-sd-animate key={index}>{character}</span>);
  return <div ref={ref}>{strong ? <strong>{spans}</strong> : spans}</div>;
}

describe('independent new-text fades', () => {
  it('keeps old animations running through updates and does not replay reparsed Markdown', async () => {
    const animations: { cancel: ReturnType<typeof vi.fn>; finished: Promise<void> }[] = [];
    const animate = vi.fn(() => {
      const animation = { cancel: vi.fn(), finished: new Promise<void>(() => {}) };
      animations.push(animation);
      return animation;
    });
    Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: animate });
    const { rerender, unmount } = render(<Harness text="" />);
    await act(async () => rerender(<Harness text="甲乙" />));
    expect(animate).toHaveBeenCalledTimes(2);
    await act(async () => rerender(<Harness text="甲乙丙" />));
    expect(animate).toHaveBeenCalledTimes(3);
    expect(animations[0].cancel).not.toHaveBeenCalled();
    await act(async () => rerender(<Harness text="甲乙丙" strong />));
    expect(animate).toHaveBeenCalledTimes(3);
    await act(async () => rerender(<Harness text="甲乙丙丁" strong />));
    expect(animate).toHaveBeenCalledTimes(4);
    unmount();
    expect(animations.every(animation => animation.cancel.mock.calls.length === 1)).toBe(true);
  });

  it('leaves history/static content visible without Web Animations support', async () => {
    const { container, rerender } = render(<Harness text="歷史" active={false} />);
    await act(async () => rerender(<Harness text="歷史新增" active={false} />));
    expect(container).toHaveTextContent('歷史新增');
  });
});
