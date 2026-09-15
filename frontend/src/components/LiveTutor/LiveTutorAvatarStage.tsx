'use client';

/**
 * Live Tutor avatar stage.
 *
 * The stage owns only the visual rendering boundary for live voice mode. It
 * shows an avatar video stream when one is available and falls back to the
 * existing AREQA logo orb for voice-only sessions, avatar-disabled sessions,
 * and provider startup gaps.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import type { LiveTutorStatus } from '@/store/liveTutor/types';
import { logger } from '@/utils/logger';
import { useStyles } from './styles';

const AVATAR_VIDEO_STALL_TIMEOUT_MS = 3_000;

export interface LiveTutorAvatarStageProps {
  /** Whether the user wants the avatar face enabled for the active session. */
  avatarEnabled: boolean;
  /** Remote media stream that carries the avatar video track, when available. */
  avatarStream: MediaStream | null;
  /** Current live tutor lifecycle state used for nonverbal visual state. */
  status: LiveTutorStatus;
  /** Presentation boundary for inline voice mode or the fixed avatar pane. */
  layout?: 'inline' | 'side-pane';
  /** Called when the attached avatar stream stops rendering usable video. */
  onStreamUnhealthy?: () => void;
}

/**
 * Render the active avatar video, or the voice-only logo fallback.
 *
 * Args:
 *   props: Avatar toggle state, optional remote video stream, and live status.
 *
 * Returns:
 *   A stable visual stage for the Live Tutor panel.
 *
 * Side Effects:
 *   Attaches and detaches the provided MediaStream to a local video element.
 *
 * Compatibility:
 *   The current OpenAI-direct Realtime client provides audio only, so the
 *   fallback is the default today. Future LiveKit/Anam integration can pass
 *   the avatar participant stream without changing the panel layout.
 */
export function LiveTutorAvatarStage({
  avatarEnabled,
  avatarStream,
  status,
  layout = 'inline',
  onStreamUnhealthy,
}: LiveTutorAvatarStageProps) {
  const { styles, cx } = useStyles();
  const videoRef = useRef<HTMLVideoElement>(null);
  const stallTimerRef = useRef<number | null>(null);
  const [readyStream, setReadyStream] = useState<MediaStream | null>(null);
  const [unhealthyStream, setUnhealthyStream] = useState<MediaStream | null>(null);

  const hasVideoTrack = useMemo(
    () => Boolean(avatarStream?.getVideoTracks().some((track) => track.readyState === 'live')),
    [avatarStream],
  );
  const showAvatar = avatarEnabled && hasVideoTrack && avatarStream !== unhealthyStream;
  const videoReady = showAvatar && readyStream === avatarStream;

  const clearStallTimer = useCallback(() => {
    if (!stallTimerRef.current) return;
    window.clearTimeout(stallTimerRef.current);
    stallTimerRef.current = null;
  }, []);

  const markUnhealthy = useCallback((reason: string) => {
    clearStallTimer();
    setUnhealthyStream(avatarStream);
    setReadyStream(null);
    logger.warn('realtime.avatar_video_unhealthy', {
      component: 'LiveTutorAvatarStage',
      layout,
      reason,
    });
    onStreamUnhealthy?.();
  }, [avatarStream, clearStallTimer, layout, onStreamUnhealthy]);

  const scheduleStallFallback = useCallback((reason: string) => {
    clearStallTimer();
    stallTimerRef.current = window.setTimeout(() => {
      markUnhealthy(reason);
    }, AVATAR_VIDEO_STALL_TIMEOUT_MS);
  }, [clearStallTimer, markUnhealthy]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = showAvatar ? avatarStream : null;
    if (showAvatar) {
      void video.play().catch(() => undefined);
    }
    return () => {
      clearStallTimer();
      video.srcObject = null;
    };
  }, [avatarStream, clearStallTimer, showAvatar]);

  useEffect(() => {
    if (!avatarStream) return;
    const tracks = avatarStream.getVideoTracks();
    const handleEnded = () => markUnhealthy('track_ended');
    const handleMuted = () => scheduleStallFallback('track_muted');
    const handleUnmuted = () => {
      clearStallTimer();
      setUnhealthyStream(null);
    };
    for (const track of tracks) {
      track.addEventListener?.('ended', handleEnded);
      track.addEventListener?.('mute', handleMuted);
      track.addEventListener?.('unmute', handleUnmuted);
    }
    return () => {
      clearStallTimer();
      for (const track of tracks) {
        track.removeEventListener?.('ended', handleEnded);
        track.removeEventListener?.('mute', handleMuted);
        track.removeEventListener?.('unmute', handleUnmuted);
      }
    };
  }, [avatarStream, clearStallTimer, markUnhealthy, scheduleStallFallback]);

  return (
    <div
      className={cx(
        styles.avatarStage,
        layout === 'side-pane' && styles.avatarStageSidePane,
        showAvatar && styles.avatarStageActive,
        showAvatar && layout === 'side-pane' && styles.avatarStageActiveSidePane,
        showAvatar && status === 'speaking' && styles.avatarStageSpeaking,
      )}
      data-avatar-state={showAvatar ? 'video' : avatarEnabled ? 'waiting' : 'fallback'}
    >
      {showAvatar && (
        <video
          ref={videoRef}
          className={cx(styles.avatarVideo, videoReady && styles.avatarVideoReady)}
          autoPlay
          muted
          playsInline
          onLoadedData={() => {
            clearStallTimer();
            setUnhealthyStream(null);
            setReadyStream(avatarStream);
          }}
          onPlaying={() => {
            clearStallTimer();
            setUnhealthyStream(null);
          }}
          onTimeUpdate={clearStallTimer}
          onWaiting={() => scheduleStallFallback('video_waiting')}
          onStalled={() => scheduleStallFallback('video_stalled')}
          onError={() => markUnhealthy('video_error')}
          aria-hidden
        />
      )}

      {(!showAvatar || !videoReady) && (
        <div className={styles.voiceCore} aria-hidden>
          <div className={styles.logoOrb}>
            <Image
              src="/icon/areqa_icon_v4_circle.png"
              alt=""
              width={192}
              height={192}
              unoptimized
              className={styles.logoImage}
              draggable={false}
              priority
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default LiveTutorAvatarStage;
