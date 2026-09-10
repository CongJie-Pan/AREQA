import { afterEach, describe, expect, it, vi } from 'vitest';
import { playLiveVoiceCue } from '@/services/realtime/sound';

const gainRamps: number[] = [];

class FakeOscillatorNode {
  type: OscillatorType = 'sine';
  frequency = {
    setValueAtTime: vi.fn(),
  };
  connect = vi.fn();
  start = vi.fn();
  stop = vi.fn();
}

class FakeGainNode {
  gain = {
    setValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn((value: number) => {
      gainRamps.push(value);
    }),
  };
  connect = vi.fn();
}

class FakeAudioContext {
  currentTime = 0;
  destination = {};
  createOscillator = vi.fn(() => new FakeOscillatorNode());
  createGain = vi.fn(() => new FakeGainNode());
  close = vi.fn(async () => undefined);
}

describe('playLiveVoiceCue', () => {
  const originalAudioContext = window.AudioContext;

  afterEach(() => {
    gainRamps.length = 0;
    vi.restoreAllMocks();
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: originalAudioContext,
    });
  });

  it('uses an audible lifecycle cue gain for connection sounds', () => {
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: FakeAudioContext,
    });

    playLiveVoiceCue('connected');

    expect(gainRamps).toContain(0.11200000000000002);
  });

  it('keeps louder lifecycle cues below the clipping guard', () => {
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: FakeAudioContext,
    });

    playLiveVoiceCue('hangup');

    const audibleRamps = gainRamps.filter((value) => value > 0.001);
    expect(Math.max(...audibleRamps)).toBeLessThanOrEqual(0.16);
    expect(audibleRamps).toEqual(expect.arrayContaining([0.096, 0.08960000000000001]));
  });
});
