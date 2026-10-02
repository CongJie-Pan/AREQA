import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';

const DEFAULT_WIDTH = 280;
const MIN_WIDTH = 220;
const CHAT_MIN_WIDTH = 420;

export function useSidebarResize() {
  const [preferredWidth, setPreferredWidth] = useState(DEFAULT_WIDTH);
  const [maxWidth, setMaxWidth] = useState(DEFAULT_WIDTH);
  const drag = useRef<{
    pointerId: number;
    startX: number;
    startWidth: number;
    cursor: string;
    userSelect: string;
  } | null>(null);
  const width = Math.min(preferredWidth, maxWidth);

  const stopResize = useCallback(() => {
    if (!drag.current) return;
    document.body.style.cursor = drag.current.cursor;
    document.body.style.userSelect = drag.current.userSelect;
    drag.current = null;
  }, []);

  useEffect(() => {
    const getMaxWidth = () => Math.max(MIN_WIDTH, window.innerWidth - CHAT_MIN_WIDTH);
    const onResize = () => {
      stopResize();
      setMaxWidth(getMaxWidth());
    };
    const onMove = (event: PointerEvent) => {
      if (!drag.current || event.pointerId !== drag.current.pointerId) return;
      setPreferredWidth(Math.min(getMaxWidth(), Math.max(
        MIN_WIDTH, drag.current.startWidth + event.clientX - drag.current.startX,
      )));
    };
    const onEnd = (event: PointerEvent) => {
      if (event.pointerId === drag.current?.pointerId) stopResize();
    };
    onResize();
    window.addEventListener('resize', onResize);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd);
    window.addEventListener('pointercancel', onEnd);
    window.addEventListener('blur', stopResize);
    return () => {
      stopResize();
      window.removeEventListener('resize', onResize);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      window.removeEventListener('pointercancel', onEnd);
      window.removeEventListener('blur', stopResize);
    };
  }, [stopResize]);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || window.innerWidth <= 768) return;
    event.preventDefault();
    stopResize();
    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: width,
      cursor: document.body.style.cursor,
      userSelect: document.body.style.userSelect,
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextWidth = event.key === 'Home' ? MIN_WIDTH
      : event.key === 'End' ? maxWidth
        : width + (event.key === 'ArrowRight' ? 16 : -16);
    setPreferredWidth(Math.min(maxWidth, Math.max(MIN_WIDTH, nextWidth)));
  };

  return { width, minWidth: MIN_WIDTH, maxWidth, startResize, stopResize, onKeyDown };
}
