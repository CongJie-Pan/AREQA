import { useEffect, useMemo, useRef, useState } from 'react';
import { logger } from '@/utils/logger';

const FRAME_MS = 32;
const MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/**
 * Reveal one message prefix across packets, paragraphs and image anchors.
 *
 * Args:
 *   content: Authoritative received Markdown; never changed by this hook.
 *   receiving: Whether this message is receiving a typed response.
 *   disabled: Bypass pacing for user messages and voice-owned captions.
 * Returns:
 *   The display prefix, pending state and mount-local animation eligibility.
 * Side effects:
 *   Owns one cancellable timer and a reduced-motion listener. Lifecycle debug
 *   logs contain only lengths, never source text or message identifiers.
 */
export function useStreamingReveal(content: string, receiving: boolean, disabled = false) {
  const [reducedMotion, setReducedMotion] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia(MOTION_QUERY).matches,
  );
  const [frame, setFrame] = useState(() => ({
    source: content, receiving, disabled, reducedMotion,
    eligible: receiving && !disabled && !reducedMotion,
    visible: receiving && !disabled && !reducedMotion ? '' : content,
  }));
  const target = useRef({ text: content, boundaries: [] as number[] });
  const cursor = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previousReceiving = useRef(false);
  const drainStep = useRef(2);
  const boundaries = useMemo(() => {
    if (typeof Intl.Segmenter === 'function') {
      return Array.from(new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(content),
        ({ index, segment }) => index + segment.length);
    }
    let offset = 0;
    return Array.from(content, character => { offset += character.length; return offset; });
  }, [content]);

  // Reconcile source replacements before children render. Completed edits and
  // voice captions must never paint one stale frame or start a playback queue.
  if (frame.source !== content || frame.receiving !== receiving || frame.disabled !== disabled
    || frame.reducedMotion !== reducedMotion) {
    const replacement = !content.startsWith(frame.source);
    const completedEdit = !receiving && !frame.receiving && frame.visible === frame.source && content !== frame.source;
    const immediate = disabled || reducedMotion || (!receiving && !frame.eligible)
      || (!receiving && (replacement || completedEdit));
    setFrame({
      source: content, receiving, disabled, reducedMotion,
      eligible: !immediate && (frame.eligible || receiving),
      visible: immediate ? content : (receiving && !frame.receiving) || replacement ? '' : frame.visible,
    });
  }

  useEffect(() => {
    const query = window.matchMedia(MOTION_QUERY);
    const change = () => setReducedMotion(query.matches);
    query.addEventListener('change', change);
    return () => query.removeEventListener('change', change);
  }, []);

  useEffect(() => {
    const replacement = !content.startsWith(target.current.text);
    const sourceChanged = content !== target.current.text;
    const started = receiving && !previousReceiving.current;
    const ended = !receiving && previousReceiving.current;
    previousReceiving.current = receiving;
    target.current = { text: content, boundaries };
    const next = boundaries.findIndex(offset => offset > frame.visible.length);
    cursor.current = next === -1 ? boundaries.length : next;

    if (disabled || reducedMotion || !frame.eligible) {
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = null;
      return;
    }
    if (started) logger.debug('streaming_reveal_started', { characterCount: boundaries.length });
    else if (replacement && receiving) logger.debug('streaming_reveal_reset', { characterCount: boundaries.length });
    if (!receiving && sourceChanged) {
      drainStep.current = Math.max(drainStep.current, Math.ceil((boundaries.length - cursor.current) / 16));
    }
    if (ended) {
      // Fix the final drain rate so a large last packet clears in about 512ms.
      drainStep.current = Math.max(2, Math.ceil((boundaries.length - cursor.current) / 16));
      logger.debug('streaming_reveal_draining', { pendingCharacters: boundaries.length - cursor.current });
      if (cursor.current === boundaries.length) logger.debug('streaming_reveal_completed', { characterCount: boundaries.length });
    }
    const tick = () => {
      timer.current = null;
      const current = target.current;
      const pending = current.boundaries.length - cursor.current;
      const step = previousReceiving.current ? Math.max(2, Math.ceil(pending / 24)) : drainStep.current;
      cursor.current = Math.min(current.boundaries.length, cursor.current + step);
      const visible = current.text.slice(0, current.boundaries[cursor.current - 1] ?? 0);
      setFrame(previous => ({ ...previous, visible }));
      if (cursor.current < current.boundaries.length) {
        timer.current = setTimeout(tick, FRAME_MS);
      } else if (!previousReceiving.current) {
        logger.debug('streaming_reveal_completed', { characterCount: current.boundaries.length });
      }
    };
    // Packet arrival updates the target without restarting the playback clock.
    if (timer.current === null && cursor.current < boundaries.length) {
      timer.current = setTimeout(tick, FRAME_MS);
    }
  }, [boundaries, content, disabled, receiving, reducedMotion, frame.eligible, frame.visible]);

  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  return {
    content: frame.visible,
    isRevealing: frame.visible.length < content.length,
    animate: frame.eligible,
  };
}
