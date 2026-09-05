/**
 * Small Web Audio cues for live voice lifecycle feedback.
 *
 * The cues are synthesized instead of loaded from static assets so live voice
 * does not add network requests or binary files. Browsers may still block audio
 * until a user gesture unlocks the audio context; in that case this module
 * fails silently because cues are non-critical UI feedback.
 */

type LiveVoiceSound = 'connected' | 'muted' | 'unmuted' | 'hangup';

interface ToneStep {
  frequency: number;
  durationMs: number;
  gain: number;
}

const SOUND_STEPS: Record<LiveVoiceSound, ToneStep[]> = {
  connected: [
    { frequency: 660, durationMs: 82, gain: 0.035 },
    { frequency: 880, durationMs: 104, gain: 0.035 },
  ],
  muted: [{ frequency: 360, durationMs: 95, gain: 0.026 }],
  unmuted: [{ frequency: 620, durationMs: 95, gain: 0.03 }],
  hangup: [
    { frequency: 520, durationMs: 75, gain: 0.03 },
    { frequency: 330, durationMs: 130, gain: 0.028 },
  ],
};

/**
 * Play a short live voice cue when browser audio is available.
 *
 * Args:
 *   sound: Lifecycle event to sonify.
 *
 * Side Effects:
 *   Creates or resumes a browser AudioContext and schedules short oscillator
 *   tones. No user text, credentials, or conversation identifiers are touched.
 */
export function playLiveVoiceCue(sound: LiveVoiceSound): void {
  if (typeof window === 'undefined') return;
  const AudioContextClass = window.AudioContext
    || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass) return;

  try {
    const context = new AudioContextClass();
    const startAt = context.currentTime + 0.01;
    let offsetSeconds = 0;
    for (const step of SOUND_STEPS[sound]) {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(step.frequency, startAt + offsetSeconds);
      gain.gain.setValueAtTime(0.0001, startAt + offsetSeconds);
      gain.gain.exponentialRampToValueAtTime(step.gain, startAt + offsetSeconds + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, startAt + offsetSeconds + step.durationMs / 1000);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(startAt + offsetSeconds);
      oscillator.stop(startAt + offsetSeconds + step.durationMs / 1000);
      offsetSeconds += step.durationMs / 1000 + 0.028;
    }
    window.setTimeout(() => {
      void context.close().catch(() => undefined);
    }, Math.ceil(offsetSeconds * 1000) + 120);
  } catch {
    // Lifecycle sounds are advisory; voice mode must keep working if Web Audio
    // is unavailable, locked by autoplay policy, or mocked by tests.
  }
}
