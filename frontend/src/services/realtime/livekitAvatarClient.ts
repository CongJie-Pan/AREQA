/**
 * Browser LiveKit client for AREQA avatar mode.
 *
 * This transport is used only when the learner explicitly enables the avatar.
 * A server-side LiveKit agent owns OpenAI Realtime and Anam; this browser
 * client only joins the room, publishes microphone audio, and subscribes to
 * the avatar worker's synchronized media tracks.
 */

import { API_CONFIG } from '@/config/api';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';
import type { RealtimeClientController, StartRealtimeClientOptions } from './client';

const AVATAR_VIDEO_READY_TIMEOUT_MS = 15_000;
const LIVEKIT_TRANSCRIPTION_TOPIC = 'lk.transcription';

interface LiveKitAvatarSessionResponse {
  livekit_url: string;
  token: string;
  room_name: string;
  participant_identity: string;
  agent_name: string;
  expires_in: number;
}

interface LiveKitTrack {
  kind: string;
  mediaStreamTrack?: MediaStreamTrack;
}

interface LiveKitTrackPublication {
  kind?: string;
}

interface LiveKitRoomLike {
  connect: (url: string, token: string) => Promise<void>;
  disconnect: () => void;
  registerTextStreamHandler?: (topic: string, callback: LiveKitTextStreamHandler) => void;
  unregisterTextStreamHandler?: (topic: string) => void;
  localParticipant: {
    setMicrophoneEnabled: (enabled: boolean) => Promise<unknown>;
  };
  on: (event: string, callback: (...args: unknown[]) => void) => LiveKitRoomLike;
}

interface LiveKitTextStreamReader {
  info?: {
    id?: string;
    attributes?: Record<string, unknown>;
  };
  [Symbol.asyncIterator]: () => AsyncIterator<string>;
}

type LiveKitTextStreamHandler = (
  reader: LiveKitTextStreamReader,
  participantInfo: { identity: string },
) => void;

interface LiveKitClientModule {
  Room: new () => LiveKitRoomLike;
  RoomEvent: {
    Connected: string;
    Disconnected: string;
    TrackSubscribed: string;
    TrackUnsubscribed: string;
  };
  Track: {
    Kind: {
      Audio: string;
      Video: string;
    };
  };
}

let liveKitClientLoader = async (): Promise<LiveKitClientModule> => (
  await import('livekit-client') as unknown as LiveKitClientModule
);

/**
 * Override the LiveKit dynamic import in tests.
 *
 * Args:
 *   loader: Deterministic module loader used by Vitest.
 *
 * Returns:
 *   Cleanup function that restores the production dynamic import.
 */
export function __setLiveKitClientLoaderForTests(
  loader: () => Promise<LiveKitClientModule>,
): () => void {
  liveKitClientLoader = loader;
  return () => {
    liveKitClientLoader = async () => (
      await import('livekit-client') as unknown as LiveKitClientModule
    );
  };
}

async function createLiveKitAvatarSession(
  conversationId: string,
  interfaceLanguage: StartRealtimeClientOptions['interfaceLanguage'],
): Promise<LiveKitAvatarSessionResponse> {
  /** Fetches only browser-safe room metadata; signed tokens are never logged. */
  const response = await authenticatedFetch(API_CONFIG.liveKitAvatarSessionEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      interface_language: interfaceLanguage,
    }),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`LiveKit avatar session failed (${response.status})${body ? `: ${body.slice(0, 240)}` : ''}`);
  }
  const payload = await response.json() as Partial<LiveKitAvatarSessionResponse>;
  if (!payload.livekit_url || !payload.token || !payload.room_name) {
    throw new Error('LiveKit avatar session response is missing connection metadata');
  }
  return payload as LiveKitAvatarSessionResponse;
}

function streamFromTrack(track: LiveKitTrack): MediaStream | null {
  // LiveKit exposes the native MediaStreamTrack; the existing avatar stage
  // expects a browser MediaStream so it can remain transport-agnostic.
  if (!track.mediaStreamTrack) return null;
  return new MediaStream([track.mediaStreamTrack]);
}

function isTrackKind(value: unknown, kind: string): boolean {
  return String(value || '').toLowerCase() === kind.toLowerCase();
}

function isFinalTranscription(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return value.toLowerCase() === 'true';
  return true;
}

async function handleLiveKitTranscriptionStream(
  reader: LiveKitTextStreamReader,
  participantIdentity: string,
  learnerIdentity: string,
  options: StartRealtimeClientOptions,
  conversationId: string,
): Promise<void> {
  const isUserTranscript = participantIdentity === learnerIdentity;
  const final = isFinalTranscription(reader.info?.attributes?.['lk.transcription_final']);
  let transcript = '';
  let assistantStarted = false;

  try {
    for await (const chunk of reader) {
      if (!chunk) continue;
      transcript += chunk;
      if (!isUserTranscript) {
        if (!assistantStarted) {
          assistantStarted = true;
          options.onAssistantResponseStarted?.();
        }
        options.onAssistantTranscriptDelta(chunk);
      }
    }

    const trimmedTranscript = transcript.trim();
    if (!trimmedTranscript || !final) return;
    if (isUserTranscript) {
      options.onUserTranscript(trimmedTranscript, reader.info?.id);
    } else {
      options.onAssistantTranscriptDone(trimmedTranscript);
    }
    logger.info('livekit.avatar_transcription_forwarded', {
      conversationId,
      source: isUserTranscript ? 'user' : 'assistant',
      final,
      transcriptChars: trimmedTranscript.length,
    });
  } catch (error) {
    logger.warn('livekit.avatar_transcription_stream_failed', {
      conversationId,
      source: isUserTranscript ? 'user' : 'assistant',
      errorMessage: error instanceof Error ? error.message : String(error),
    });
  }
}

/**
 * Start a LiveKit-backed avatar voice session.
 *
 * Args:
 *   options: The same Live Tutor callbacks used by the OpenAI-direct client.
 *
 * Returns:
 *   A controller for muting and disconnecting the LiveKit room.
 *
 * Raises:
 *   Errors are reported through `options.onError`; the returned no-op
 *   controller keeps LiveTutorPanel cleanup idempotent after setup failures.
 *
 * Side Effects:
 *   Fetches a short-lived LiveKit token, connects to a room, publishes local
 *   microphone audio, and forwards subscribed remote audio/video tracks to the
 *   existing Live Tutor playback and avatar stage callbacks. Logs use stable
 *   `livekit.avatar_*` event names with safe metadata only.
 */
export async function startLiveKitAvatarClient(
  options: StartRealtimeClientOptions,
): Promise<RealtimeClientController> {
  let room: LiveKitRoomLike | null = null;
  let muted = false;
  let avatarVideoReady = false;
  let resolveAvatarVideoReady: (() => void) | null = null;
  let avatarVideoReadyTimeout: number | null = null;
  const conversationId = options.getConversationId?.() || options.conversationId;
  const avatarVideoReadyPromise = new Promise<void>((resolve, reject) => {
    resolveAvatarVideoReady = () => {
      if (avatarVideoReadyTimeout) window.clearTimeout(avatarVideoReadyTimeout);
      avatarVideoReadyTimeout = null;
      resolve();
    };
    avatarVideoReadyTimeout = window.setTimeout(() => {
      if (avatarVideoReady) return;
      avatarVideoReadyTimeout = null;
      reject(new Error(`LiveKit avatar video track was not received within ${AVATAR_VIDEO_READY_TIMEOUT_MS}ms`));
    }, AVATAR_VIDEO_READY_TIMEOUT_MS);
  });

  try {
    options.onStatus('connecting');
    const session = await createLiveKitAvatarSession(options.conversationId, options.interfaceLanguage);
    const livekit = await liveKitClientLoader();
    room = new livekit.Room();
    room.registerTextStreamHandler?.(LIVEKIT_TRANSCRIPTION_TOPIC, (reader, participantInfo) => {
      void handleLiveKitTranscriptionStream(
        reader,
        participantInfo.identity,
        session.participant_identity,
        options,
        conversationId,
      );
    });
    logger.info('livekit.avatar_transcription_handler_registered', {
      conversationId,
      roomName: session.room_name,
      topic: LIVEKIT_TRANSCRIPTION_TOPIC,
    });

    room
      .on(livekit.RoomEvent.Connected, () => {
        logger.info('livekit.avatar_room_connected', {
          conversationId,
          roomName: session.room_name,
          agentName: session.agent_name,
        });
        options.onStatus('listening');
      })
      .on(livekit.RoomEvent.Disconnected, () => {
        logger.info('livekit.avatar_room_disconnected', {
          conversationId,
          roomName: session.room_name,
        });
        options.onStatus('connected');
      })
      .on(livekit.RoomEvent.TrackSubscribed, (trackArg, publicationArg) => {
        const track = trackArg as LiveKitTrack;
        const publication = publicationArg as LiveKitTrackPublication | undefined;
        const stream = streamFromTrack(track);
        if (!stream) return;
        const kind = track.kind || publication?.kind;
        if (isTrackKind(kind, livekit.Track.Kind.Audio)) {
          options.onRemoteStream(stream);
          options.onPlaybackState?.('started');
          options.onStatus('speaking');
        }
        if (isTrackKind(kind, livekit.Track.Kind.Video)) {
          avatarVideoReady = true;
          options.onRemoteVideoStream?.(stream);
          resolveAvatarVideoReady?.();
          logger.info('livekit.avatar_video_track_subscribed', {
            conversationId,
            roomName: session.room_name,
          });
        }
      })
      .on(livekit.RoomEvent.TrackUnsubscribed, (_trackArg, publicationArg) => {
        const publication = publicationArg as LiveKitTrackPublication | undefined;
        if (isTrackKind(publication?.kind, livekit.Track.Kind.Audio)) {
          options.onPlaybackState?.('stopped');
          options.onStatus('listening');
        }
      });

    await room.connect(session.livekit_url, session.token);
    await room.localParticipant.setMicrophoneEnabled(true);
    if (muted) await room.localParticipant.setMicrophoneEnabled(false);
    logger.info('livekit.avatar_microphone_enabled', {
      conversationId,
      roomName: session.room_name,
      participantIdentity: session.participant_identity,
    });
    await avatarVideoReadyPromise;

    return {
      setMuted: (nextMuted: boolean) => {
        muted = nextMuted;
        void room?.localParticipant.setMicrophoneEnabled(!nextMuted);
      },
      cancelSpeech: () => undefined,
      disconnect: () => {
        room?.unregisterTextStreamHandler?.(LIVEKIT_TRANSCRIPTION_TOPIC);
        room?.disconnect();
        room = null;
      },
    };
  } catch (error) {
    if (avatarVideoReadyTimeout) window.clearTimeout(avatarVideoReadyTimeout);
    room?.unregisterTextStreamHandler?.(LIVEKIT_TRANSCRIPTION_TOPIC);
    room?.disconnect();
    const nextError = error instanceof Error ? error : new Error(String(error));
    logger.error('livekit.avatar_session_failed', nextError, { conversationId });
    options.onError(nextError);
    return {
      setMuted: () => undefined,
      cancelSpeech: () => undefined,
      disconnect: () => undefined,
    };
  }
}
