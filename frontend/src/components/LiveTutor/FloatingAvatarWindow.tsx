'use client';

/**
 * Draggable floating video window for Live Tutor avatar mode.
 *
 * The component keeps avatar video out of the composer layout so the remote
 * face cannot cover the text input by default. Desktop positions are persisted;
 * mobile positions are reset each session because browser chrome and virtual
 * keyboards make stored coordinates unreliable.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GripHorizontal } from 'lucide-react';
import type { LiveTutorStatus } from '@/store/liveTutor/types';
import { logger } from '@/utils/logger';
import { useStyles } from './styles';

const STORAGE_KEY = 'areqa:live-tutor-avatar-window-position';
const DESKTOP_DEFAULT_OFFSET = { right: 32, bottom: 104 };
const MOBILE_DEFAULT_OFFSET = { right: 16, bottom: 112 };
const VIEWPORT_MARGIN = 12;

interface AvatarPosition {
  x: number;
  y: number;
}

export interface FloatingAvatarWindowProps {
  /** Remote media stream carrying the avatar video track. */
  stream: MediaStream;
  /** Current Live Tutor lifecycle state for visual emphasis. */
  status: LiveTutorStatus;
}

function isMobileViewport(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(max-width: 768px)').matches;
}

function defaultPosition(size: { width: number; height: number }, mobile: boolean): AvatarPosition {
  const offset = mobile ? MOBILE_DEFAULT_OFFSET : DESKTOP_DEFAULT_OFFSET;
  return {
    x: Math.max(VIEWPORT_MARGIN, window.innerWidth - size.width - offset.right),
    y: Math.max(VIEWPORT_MARGIN, window.innerHeight - size.height - offset.bottom),
  };
}

function clampPosition(position: AvatarPosition, size: { width: number; height: number }): AvatarPosition {
  const maxX = Math.max(VIEWPORT_MARGIN, window.innerWidth - size.width - VIEWPORT_MARGIN);
  const maxY = Math.max(VIEWPORT_MARGIN, window.innerHeight - size.height - VIEWPORT_MARGIN);
  return {
    x: Math.min(Math.max(position.x, VIEWPORT_MARGIN), maxX),
    y: Math.min(Math.max(position.y, VIEWPORT_MARGIN), maxY),
  };
}

function storedDesktopPosition(): AvatarPosition | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AvatarPosition>;
    if (typeof parsed.x !== 'number' || typeof parsed.y !== 'number') return null;
    return { x: parsed.x, y: parsed.y };
  } catch {
    return null;
  }
}

function persistDesktopPosition(position: AvatarPosition): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(position));
  } catch {
    // Persisting the window position is a convenience, not a session boundary.
  }
}

/**
 * Render a movable avatar video surface anchored above the composer.
 *
 * Args:
 *   props: Remote avatar stream and current voice status.
 *
 * Returns:
 *   A fixed-position video window with a drag handle.
 *
 * Side Effects:
 *   Attaches the remote MediaStream to a video element and persists desktop
 *   drag coordinates to localStorage.
 */
export function FloatingAvatarWindow({ stream, status }: FloatingAvatarWindowProps) {
  const { styles, cx } = useStyles();
  const rootRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    offsetX: number;
    offsetY: number;
    width: number;
    height: number;
  } | null>(null);
  const mobile = useMemo(() => isMobileViewport(), []);
  const [position, setPosition] = useState<AvatarPosition | null>(() => {
    if (typeof window === 'undefined') return null;
    const size = {
      width: mobile ? 176 : 240,
      height: mobile ? 220 : 300,
    };
    const initialPosition = mobile ? null : storedDesktopPosition();
    return clampPosition(initialPosition ?? defaultPosition(size, mobile), size);
  });

  const resolveDefaultPosition = useCallback((): AvatarPosition => {
    const rect = rootRef.current?.getBoundingClientRect();
    const size = {
      width: rect?.width || (mobile ? 176 : 240),
      height: rect?.height || (mobile ? 220 : 300),
    };
    return defaultPosition(size, mobile);
  }, [mobile]);

  const resetPosition = useCallback(() => {
    setPosition(resolveDefaultPosition());
  }, [resolveDefaultPosition]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    void video.play().catch(() => undefined);
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  useEffect(() => {
    const handleResize = () => {
      const rect = rootRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPosition((current) => clampPosition(current ?? defaultPosition(rect, mobile), rect));
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [mobile]);

  const handlePointerDown = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
      width: rect.width,
      height: rect.height,
    };
    logger.info('realtime.avatar_window_drag_started', {
      component: 'FloatingAvatarWindow',
      mobile,
    });
  }, [mobile]);

  const handlePointerMove = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const nextPosition = clampPosition({
      x: event.clientX - drag.offsetX,
      y: event.clientY - drag.offsetY,
    }, drag);
    setPosition(nextPosition);
  }, []);

  const handlePointerUp = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setPosition((current) => {
      const nextPosition = clampPosition(current ?? defaultPosition(drag, mobile), drag);
      if (!mobile) persistDesktopPosition(nextPosition);
      logger.info('realtime.avatar_window_drag_finished', {
        component: 'FloatingAvatarWindow',
        mobile,
      });
      return nextPosition;
    });
  }, [mobile]);

  return (
    <div
      ref={rootRef}
      className={cx(styles.floatingAvatarWindow, status === 'speaking' && styles.floatingAvatarSpeaking)}
      data-avatar-window="floating"
      style={position ? { transform: `translate3d(${Math.round(position.x)}px, ${Math.round(position.y)}px, 0)` } : undefined}
    >
      <button
        type="button"
        className={styles.floatingAvatarHandle}
        aria-label="Move avatar window"
        title="Move avatar window"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onDoubleClick={resetPosition}
      >
        <GripHorizontal size={16} aria-hidden />
      </button>
      <video
        ref={videoRef}
        className={styles.floatingAvatarVideo}
        autoPlay
        muted
        playsInline
        aria-label="AREQA avatar video"
      />
    </div>
  );
}

export default FloatingAvatarWindow;
