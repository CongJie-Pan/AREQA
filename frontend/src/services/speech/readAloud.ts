/**
 * Text-to-speech client for assistant reply read-out.
 *
 * The speech API streams MP3 as the provider generates it. Where the browser
 * supports Media Source Extensions for MP3 (MediaSource, or Safari's
 * ManagedMediaSource) playback starts on the first chunk; otherwise the whole
 * file is downloaded first and played from a blob, as before.
 */

import { API_CONFIG } from '@/config/api';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { normalizeReadbackText } from '@/services/realtime/readbackText';
import { logger } from '@/utils/logger';

const MP3_MIME = 'audio/mpeg';
/** Seconds of already-played audio kept when the browser's buffer is full. */
const PLAYED_AUDIO_TO_KEEP_S = 10;
const BUFFER_FULL_RETRY_MS = 500;

export type ReadAloudPlaybackMode = 'stream' | 'buffered';

export interface ReadAloudPlayback {
  audio: HTMLAudioElement;
  mode: ReadAloudPlaybackMode;
  /** Stop downloading and release the object URL. Safe to call twice. */
  dispose: () => void;
}

export function prepareReadAloudText(markdown: string): string {
  return normalizeReadbackText(markdown);
}

async function requestReadAloud(markdown: string, signal?: AbortSignal): Promise<Response> {
  const text = prepareReadAloudText(markdown);
  if (!text) {
    throw new Error('No readable text');
  }

  const response = await authenticatedFetch(API_CONFIG.speechReadAloudEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!response.ok) {
    throw new Error('Read aloud failed');
  }
  return response;
}

/** Download the whole read-out as one MP3 blob. */
export async function createReadAloudAudio(markdown: string, signal?: AbortSignal): Promise<Blob> {
  const response = await requestReadAloud(markdown, signal);
  return response.blob();
}

type MediaSourceConstructor = typeof MediaSource;

function streamingMediaSource(): MediaSourceConstructor | null {
  if (typeof window === 'undefined') return null;
  const scope = window as unknown as {
    ManagedMediaSource?: MediaSourceConstructor;
    MediaSource?: MediaSourceConstructor;
  };
  const candidates = [scope.ManagedMediaSource, scope.MediaSource];
  return candidates.find((ctor) => typeof ctor?.isTypeSupported === 'function' && ctor.isTypeSupported(MP3_MIME)) ?? null;
}

function waitForEvent(target: EventTarget, type: string): Promise<void> {
  return new Promise((resolve) => target.addEventListener(type, () => resolve(), { once: true }));
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Append one chunk. Browsers cap audio buffers (about 12 MB in Chrome), so a
 * long read-out drops audio that has already played and retries.
 */
async function appendChunk(buffer: SourceBuffer, chunk: Uint8Array, audio: HTMLAudioElement, isDisposed: () => boolean) {
  while (!isDisposed()) {
    try {
      buffer.appendBuffer(chunk as BufferSource);
      await waitForEvent(buffer, 'updateend');
      return;
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== 'QuotaExceededError') throw error;
      const removeUntil = audio.currentTime - PLAYED_AUDIO_TO_KEEP_S;
      if (removeUntil > 0 && buffer.buffered.length > 0 && buffer.buffered.start(0) < removeUntil) {
        buffer.remove(0, removeUntil);
        await waitForEvent(buffer, 'updateend');
      } else {
        await delay(BUFFER_FULL_RETRY_MS);
      }
    }
  }
}

function streamIntoAudio(body: ReadableStream<Uint8Array>, MediaSourceCtor: MediaSourceConstructor): ReadAloudPlayback {
  const mediaSource = new MediaSourceCtor();
  const objectUrl = URL.createObjectURL(mediaSource);
  const audio = new Audio();
  // Safari's ManagedMediaSource only plays when remote playback is off.
  audio.disableRemotePlayback = true;
  audio.src = objectUrl;

  const reader = body.getReader();
  let disposed = false;
  const isDisposed = () => disposed;
  const startedAt = performance.now();

  const pump = async () => {
    await waitForEvent(mediaSource, 'sourceopen');
    const buffer = mediaSource.addSourceBuffer(MP3_MIME);
    let firstChunk = true;
    while (!disposed) {
      const { done, value } = await reader.read();
      if (done || disposed) break;
      if (firstChunk) {
        firstChunk = false;
        logger.info('read_aloud_first_audio', {
          component: 'readAloud',
          elapsedMs: Math.round(performance.now() - startedAt),
        });
      }
      await appendChunk(buffer, value, audio, isDisposed);
    }
    if (!disposed && mediaSource.readyState === 'open') mediaSource.endOfStream();
  };

  void pump().catch((error: unknown) => {
    if (disposed) return;
    logger.warn('read_aloud_stream_failed', {
      component: 'readAloud',
      reason: error instanceof Error ? error.name : 'unknown',
    });
    // Ends playback with what has arrived; the player's error/ended handlers clean up.
    if (mediaSource.readyState === 'open') mediaSource.endOfStream('network');
  });

  return {
    audio,
    mode: 'stream',
    dispose: () => {
      if (disposed) return;
      disposed = true;
      void reader.cancel().catch(() => undefined);
      URL.revokeObjectURL(objectUrl);
    },
  };
}

/**
 * Request a read-out and return an audio element ready to play. The caller
 * calls `audio.play()` and must call `dispose()` when playback stops.
 */
export async function startReadAloudPlayback(markdown: string, signal?: AbortSignal): Promise<ReadAloudPlayback> {
  const response = await requestReadAloud(markdown, signal);
  const MediaSourceCtor = streamingMediaSource();

  if (MediaSourceCtor && response.body) {
    logger.info('read_aloud_playback_mode', { component: 'readAloud', mode: 'stream' });
    return streamIntoAudio(response.body, MediaSourceCtor);
  }

  // Fallback for browsers without MP3 Media Source support.
  logger.info('read_aloud_playback_mode', { component: 'readAloud', mode: 'buffered' });
  const objectUrl = URL.createObjectURL(await response.blob());
  let released = false;
  return {
    audio: new Audio(objectUrl),
    mode: 'buffered',
    dispose: () => {
      if (released) return;
      released = true;
      URL.revokeObjectURL(objectUrl);
    },
  };
}
