import { useEffect, useMemo, useRef, useState } from 'react';
import type { DisplayMessage } from '@/store/chat';

const LATIN_CHARACTER_MS = 65;
const CJK_CHARACTER_MS = 180;
const SENTENCE_PAUSE_MS = 180;

/**
 * Pace live speech captions against playback boundaries, preserving full history.
 *
 * Args:
 *   content: Latest authoritative transcript, including done-only responses.
 *   playback: Ephemeral audio state; absent for historical and typed messages.
 *   voiceCaption: Exact sentence prefix released by queued playback, when available.
 * Returns:
 *   A progressively revealed prefix. Realtime provides no word timestamps, so
 *   pacing is estimated and catches up smoothly when the audio buffer drains.
 * Side effects:
 *   Owns one cancellable timer. Never delays persistence or mutates chat history.
 */
export function useVoiceReveal(content: string, playback: DisplayMessage['voicePlayback'], voiceCaption?: string): string {
  const [length, setLength] = useState(0);
  const characters = useMemo(() => Array.from(content), [content]);
  const targetRef = useRef(characters);
  const lengthRef = useRef(0);
  useEffect(() => { targetRef.current = characters; }, [characters]);
  useEffect(() => {
    if (!playback || playback === 'interrupted' || playback === 'waiting' || voiceCaption !== undefined) return;
    if (playback === 'finished') {
      lengthRef.current = targetRef.current.length;
      setLength(lengthRef.current);
      return;
    }
    let elapsed = 0;
    // Incoming deltas update the target without restarting the playback clock.
    const timer = window.setInterval(() => {
      const target = targetRef.current;
      if (lengthRef.current >= target.length) { elapsed = Math.min(elapsed, 0); return; }
      elapsed += 10;
      const previous = target[lengthRef.current - 1] || '';
      const delay = (/[\u3400-\u9fff]/u.test(target[lengthRef.current] || '') ? CJK_CHARACTER_MS : LATIN_CHARACTER_MS)
        + (/[.!?。！？]/u.test(previous) ? SENTENCE_PAUSE_MS : 0);
      if (elapsed < delay) return;
      elapsed -= delay;
      lengthRef.current = Math.min(target.length, lengthRef.current + 1);
      setLength(lengthRef.current);
    }, 10);
    return () => window.clearInterval(timer);
  }, [playback, voiceCaption]);
  if (playback && voiceCaption !== undefined) return voiceCaption;
  return playback ? characters.slice(0, length).join('') : content;
}
