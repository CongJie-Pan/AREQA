import { afterEach, describe, expect, it, vi } from 'vitest';
import { SpeechQueue } from '@/services/realtime/speechQueue';

afterEach(() => vi.useRealTimers());

function setup() {
  vi.useFakeTimers();
  const callbacks = { id: 'turn-1', speak: vi.fn(() => true), caption: vi.fn(), complete: vi.fn() };
  return { queue: new SpeechQueue(callbacks), ...callbacks };
}

describe('sentence readback ownership', () => {
  it('starts a complete sentence before upstream finishes and waits for playout before the next', () => {
    const { queue, speak, caption, complete } = setup();
    queue.append('First sentence. ');
    expect(speak).toHaveBeenCalledWith('First sentence.', 'turn-1:1');
    queue.append('Second sentence.');
    queue.finish();
    expect(speak).toHaveBeenCalledTimes(1);
    expect(caption).not.toHaveBeenCalled();
    queue.responseStarted('r1', 'turn-1:1');
    queue.playback('started', 'r1');
    expect(caption).toHaveBeenCalledWith('First sentence.');
    queue.responseDone('r1', 'completed');
    expect(speak).toHaveBeenCalledTimes(1);
    queue.playback('stopped', 'r1');
    expect(speak).toHaveBeenLastCalledWith('Second sentence.', 'turn-1:2');
    queue.responseStarted('r2', 'turn-1:2');
    queue.playback('stopped', 'r1');
    queue.responseDone('r1', 'completed');
    expect(complete).not.toHaveBeenCalled();
    queue.playback('started', 'r2');
    queue.playback('stopped', 'r2');
    expect(complete).not.toHaveBeenCalled();
    queue.responseDone('r2', 'completed');
    expect(complete).toHaveBeenCalledWith(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('discards queued and late text on interruption without replaying', () => {
    const { queue, speak, caption } = setup();
    queue.append('One. Two. ');
    queue.responseStarted('r1', 'turn-1:1');
    queue.cancel();
    queue.append('Late. ');
    queue.finish();
    queue.playback('started', 'r1');
    queue.playback('stopped', 'r1');
    queue.responseDone('r1', 'completed');
    expect(speak).toHaveBeenCalledTimes(1);
    expect(caption).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('fails soft on rejected speech and missing completion events without retrying', () => {
    const { queue, speak, complete } = setup();
    speak.mockReturnValue(false);
    queue.append('First. ');
    queue.append('Second. ');
    queue.finish();
    expect(complete).toHaveBeenCalledWith(true);
    expect(speak).toHaveBeenCalledTimes(1);
    const next = setup();
    next.queue.append('Waiting. ');
    vi.advanceTimersByTime(90_000);
    expect(next.complete).toHaveBeenCalledWith(true);
    expect(next.speak).toHaveBeenCalledTimes(1);
  });

  it('keeps split decimals and Chinese sentences intact and normalizes markdown', () => {
    const { queue, speak } = setup();
    queue.append('The value is 3.');
    expect(speak).not.toHaveBeenCalled();
    queue.append('14. **下一句**。');
    queue.finish();
    expect(speak).toHaveBeenCalledWith('The value is 3.14.', 'turn-1:1');
    queue.cancel();
  });
});
