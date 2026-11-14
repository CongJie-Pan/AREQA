import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';

const DEFAULT_WIDTH = 280;
const MIN_WIDTH = 220;
const MAX_WIDTH = 420;
const CHAT_MIN_WIDTH = 420;

export function useSidebarResize(onCollapse?: () => void) {
  const [preferredWidth, setPreferredWidth] = useState(DEFAULT_WIDTH);
  const [maxWidth, setMaxWidth] = useState(DEFAULT_WIDTH);
  const drag = useRef<{
    pointerId: number;
    startX: number;
    startWidth: number;
    preferredWidth: number;
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
    const getMaxWidth = () => Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - CHAT_MIN_WIDTH));
    const onResize = () => {
      stopResize();
      setMaxWidth(getMaxWidth());
    };
    const collapseAtMinimum = (event: PointerEvent) => {
      const current = drag.current;
      if (!onCollapse || !current || event.clientX >= current.startX) return false;
      if (current.startWidth + event.clientX - current.startX > MIN_WIDTH) return false;
      stopResize();
      setPreferredWidth(current.preferredWidth);
      onCollapse();
      return true;
    };
    const onMove = (event: PointerEvent) => {
      const current = drag.current;
      if (!current || event.pointerId !== current.pointerId || collapseAtMinimum(event)) return;
      setPreferredWidth(Math.min(getMaxWidth(), Math.max(
        MIN_WIDTH, current.startWidth + event.clientX - current.startX,
      )));
    };
    const onEnd = (event: PointerEvent) => {
      if (event.pointerId !== drag.current?.pointerId) return;
      if (event.type !== 'pointerup' || !collapseAtMinimum(event)) stopResize();
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
  }, [onCollapse, stopResize]);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || window.innerWidth <= 768) return;
    event.preventDefault();
    stopResize();
    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: width,
      preferredWidth,
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
