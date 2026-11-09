import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MessageItem } from '@/components/MessageList/MessageItem';

vi.mock('@/components/MessageList/styles', () => ({
  useStyles: () => ({ styles: {}, cx: (...values: unknown[]) => values.filter(Boolean).join(' ') }),
}));

const message = { id: 'cascade', role: 'assistant' as const, content: '', createdAt: Date.now() };
const advance = (milliseconds: number) => act(async () => { vi.advanceTimersByTime(milliseconds); });

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('message-wide streaming cascade', () => {
  it('reveals a prefix across paragraphs instead of starting both paragraphs together', async () => {
    const first = '甲'.repeat(80);
    const second = '乙'.repeat(40);
    const { container } = render(<MessageItem message={{ ...message, content: `${first}\n\n${second}` }} isStreaming />);
    expect(container.textContent).not.toContain(first);
    await advance(320);
    expect(container.textContent).toContain('甲');
    expect(container.textContent).not.toContain('乙');
    await advance(3000);
    expect(container.textContent).toContain(first);
    expect(container.textContent).toContain(second);
  });

  it('drains the final batch without replacing already mounted text nodes', async () => {
    const initial = '甲'.repeat(80);
    const { container, rerender } = render(<MessageItem message={{ ...message, content: initial }} isStreaming />);
    await advance(96);
    const firstSpan = container.querySelector('[data-sd-animate]');
    expect(firstSpan).not.toBeNull();
    const before = container.querySelector('[data-role="assistant-bubble"]')?.textContent;
    rerender(<MessageItem message={{ ...message, content: `${initial}\n\n最後一段` }} isStreaming={false} />);
    expect(container.querySelector('[data-role="assistant-bubble"]')?.textContent).toBe(before);
    expect(container.querySelector('[data-sd-animate]')).toBe(firstSpan);
    await advance(1000);
    expect(container.textContent).toContain('最後一段');
    expect(container.querySelector('[data-sd-animate]')).toBe(firstSpan);
  });

  it('waits for the shared text cursor before revealing a future image slot', async () => {
    const before = '甲'.repeat(80);
    const live = {
      ...message, content: `${before}\n\n圖片後段`,
      streamImageSlots: [{ slotId: 'image-one', anchorAfterParagraph: 0, contentOffset: before.length }],
    };
    const { container } = render(<MessageItem message={live} isStreaming />);
    expect(container.querySelector('[data-live-answer-part="live-image-image-one"]')).toBeNull();
    await advance(320);
    expect(container.querySelector('[data-live-answer-part="live-image-image-one"]')).toBeNull();
    expect(container.textContent).not.toContain('圖片後段');
    await advance(3000);
    expect(container.querySelector('[data-live-answer-part="live-image-image-one"]')).not.toBeNull();
    expect(container.textContent).toContain('圖片後段');
  });

  it('keeps historical messages immediate and follows the voice-owned caption boundary', () => {
    const history = render(<MessageItem message={{ ...message, content: '完整歷史回答' }} />);
    const { container } = history;
    expect(container.textContent).toContain('完整歷史回答');
    expect(container.querySelector('[data-sd-animate]')).toBeNull();
    history.unmount();
    const voice = render(<MessageItem message={{ ...message, id: 'voice', content: 'First. Second.', voicePlayback: 'playing', voiceCaption: 'First.' }} isStreaming />);
    expect(voice.container.textContent).toContain('First.');
    expect(voice.container.textContent).not.toContain('Second.');
  });
});
