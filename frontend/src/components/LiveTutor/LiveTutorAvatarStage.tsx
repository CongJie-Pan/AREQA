'use client';

/**
 * Live Tutor avatar stage.
 *
 * The stage owns only the visual rendering boundary for live voice mode. It
 * shows an avatar video stream when one is available and falls back to the
 * existing AREQA logo orb for voice-only sessions, avatar-disabled sessions,
 * and provider startup gaps.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import type { LiveTutorStatus } from '@/store/liveTutor/types';
import { useStyles } from './styles';

export interface LiveTutorAvatarStageProps {
  /** Whether the user wants the avatar face enabled for the active session. */
  avatarEnabled: boolean;
  /** Remote media stream that carries the avatar video track, when available. */
  avatarStream: MediaStream | null;
  /** Current live tutor lifecycle state used for nonverbal visual state. */
  status: LiveTutorStatus;
  /** Presentation boundary for inline voice mode or the fixed avatar pane. */
  layout?: 'inline' | 'side-pane';
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
}: LiveTutorAvatarStageProps) {
  const { styles, cx } = useStyles();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [readyStream, setReadyStream] = useState<MediaStream | null>(null);

  const hasVideoTrack = useMemo(
    () => Boolean(avatarStream?.getVideoTracks().some((track) => track.readyState === 'live')),
    [avatarStream],
  );
  const showAvatar = avatarEnabled && hasVideoTrack;
  const videoReady = showAvatar && readyStream === avatarStream;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = showAvatar ? avatarStream : null;
    if (showAvatar) {
      void video.play().catch(() => undefined);
    }
    return () => {
      video.srcObject = null;
    };
  }, [avatarStream, showAvatar]);

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
          onLoadedData={() => setReadyStream(avatarStream)}
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
