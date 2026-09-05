import { useEffect, useMemo, useRef, useState } from 'react';
import type { DisplayMessage } from '@/store/chat';

/**
 * Pace live speech captions against playback boundaries, preserving full history.
 *
 * Args:
 *   content: Latest authoritative transcript, including done-only responses.
 *   playback: Ephemeral audio state; absent for historical and typed messages.
 * Returns:
 *   A progressively revealed prefix. Realtime provides no word timestamps, so
 *   pacing is estimated and catches up smoothly when the audio buffer drains.
 * Side effects:
 *   Owns one cancellable timer. Never delays persistence or mutates chat history.
 */
export function useVoiceReveal(content: string, playback: DisplayMessage['voicePlayback']): string {
  const [length, setLength] = useState(0);
  const characters = useMemo(() => Array.from(content), [content]);
  const targetRef = useRef(characters);
  const lengthRef = useRef(0);
  useEffect(() => { targetRef.current = characters; }, [characters]);
  useEffect(() => {
    if (!playback || playback === 'interrupted') return;
    let elapsed = playback === 'waiting' ? -700 : 0;
    // Incoming deltas update the target without restarting the playback clock.
    const timer = window.setInterval(() => {
      const target = targetRef.current;
      if (lengthRef.current >= target.length) { elapsed = Math.min(elapsed, 0); return; }
      elapsed += 10;
      const delay = playback === 'finished' ? 20
        : /[\u3400-\u9fff]/u.test(target[lengthRef.current] || '') ? 110 : 45;
      if (elapsed < delay) return;
      elapsed -= delay;
      const step = playback === 'finished' ? Math.max(1, Math.ceil((target.length - lengthRef.current) / 30)) : 1;
      lengthRef.current = Math.min(target.length, lengthRef.current + step);
      setLength(lengthRef.current);
    }, 10);
    return () => window.clearInterval(timer);
  }, [playback]);
  return playback ? characters.slice(0, length).join('') : content;
}
