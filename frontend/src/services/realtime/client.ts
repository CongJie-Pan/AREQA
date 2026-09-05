/**
 * Browser WebRTC client for AREQA Live Tutor.
 *
 * This module uses the low-level OpenAI Realtime WebRTC interface directly so
 * the MVP does not need an additional frontend SDK. It owns peer connection,
 * media, data-channel events, and the browser-side `get_areqa_context` tool
 * bridge.
 */

import { API_CONFIG } from '@/config/api';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import type { DisplayMessage } from '@/store/chat';
import { logger } from '@/utils/logger';
import { buildRealtimeContext } from './context';

const OPENAI_REALTIME_CALLS_URL = 'https://api.openai.com/v1/realtime/calls';
const MODEL = 'gpt-realtime-2.1-mini';
const MAX_REALTIME_ERROR_BODY_CHARS = 500;
const MAX_PROVIDER_ERROR_CODE_CHARS = 80;

export type RealtimeClientErrorCode =
  | 'microphone_denied'
  | 'microphone_insecure_context'
  | 'microphone_unavailable'
  | 'microphone_busy'
  | 'provider_error';

/** Error with a stable code that the UI can localize without parsing text. */
export class RealtimeClientError extends Error {
  /**
   * Creates a browser-safe Realtime error.
   *
   * @param code - Stable client-facing failure category.
   * @param message - Safe diagnostic message without transcript or credentials.
   */
  constructor(public readonly code: RealtimeClientErrorCode, message: string) {
    super(message);
    this.name = 'RealtimeClientError';
  }
}

export type RealtimeStatus =
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'error';

export interface StartRealtimeClientOptions {
  conversationId: string;
  getConversationId?: () => string;
  interfaceLanguage: 'zh-TW' | 'zh-CN' | 'en';
  recentMessages: () => DisplayMessage[];
  onRemoteStream: (stream: MediaStream) => void;
  onInputAudioLevel?: (level: number) => void;
  onOutputAudioLevel?: (level: number) => void;
  onPlaybackState?: (state: 'started' | 'stopped' | 'interrupted') => void;
  onStatus: (status: RealtimeStatus) => void;
  onAssistantResponseStarted?: () => void;
  onUserTurnCommitted?: (itemId: string) => void;
  onUserTranscript: (transcript: string, itemId?: string) => void;
  onAssistantTranscriptDelta: (delta: string) => void;
  onAssistantTranscriptDone: (transcript: string) => void;
  onError: (error: Error) => void;
}

export interface RealtimeClientController {
  setMuted: (muted: boolean) => void;
  disconnect: () => void;
}

interface RealtimeSessionResponse {
  client_secret: string;
  model: string;
  voice: string;
  expires_at?: string | null;
}

interface RealtimeEvent {
  type?: string;
  item_id?: string;
  transcript?: string;
  text?: string;
  delta?: string;
  call_id?: string;
  name?: string;
  arguments?: string;
  error?: {
    type?: string;
    code?: string;
    message?: string;
  };
  item?: {
    type?: string;
    call_id?: string;
    name?: string;
    arguments?: string;
  };
  response?: {
    output?: Array<{
      type?: string;
      role?: string;
      content?: Array<{
        type?: string;
        text?: string;
        transcript?: string;
      }>;
    }>;
  };
}

/**
 * Extracts the authoritative assistant transcript from a completed response.
 *
 * Realtime transports may emit transcript deltas, a transcript-only done
 * event, or only the final response output. Supporting all three prevents a
 * valid spoken answer from disappearing when intermediate events are omitted.
 *
 * @param event - Provider event parsed from the Realtime data channel.
 * @returns Concatenated assistant text, or an empty string when unavailable.
 */
function completedResponseTranscript(event: RealtimeEvent): string {
  return (event.response?.output ?? [])
    .filter((item) => item.type === 'message' && item.role === 'assistant')
    .flatMap((item) => item.content ?? [])
    .map((content) => content.transcript || content.text || '')
    .join('')
    .trim();
}

function realtimeFailureMessage(stage: 'session' | 'sdp', status: number, body = ''): string {
  const details = body ? ` ${body.slice(0, MAX_REALTIME_ERROR_BODY_CHARS)}` : '';
  if (status === 429) {
    return stage === 'sdp'
      ? 'Realtime SDP negotiation was rate limited (429). Please wait and try again, or check OpenAI Realtime quota/model access.'
      : 'Realtime session creation was rate limited (429). Please wait and try again, or check OpenAI Realtime quota/model access.';
  }
  if (status === 401 || status === 403) {
    return `Realtime ${stage} authorization failed (${status}). Check OpenAI Realtime model access and API key permissions.`;
  }
  return `Realtime ${stage} failed (${status}).${details}`;
}

/** Maps browser capture failures to stable, localizable error categories. */
function microphoneAccessError(error: unknown): Error {
  const browserError = error instanceof Error ? error : new Error(String(error));
  if (typeof window !== 'undefined' && window.isSecureContext === false) {
    return new RealtimeClientError(
      'microphone_insecure_context',
      'Microphone access requires a secure HTTPS connection',
    );
  }
  if (
    browserError.name === 'NotAllowedError'
    || browserError.name === 'SecurityError'
    || browserError.message.toLowerCase().includes('permission')
  ) {
    return new RealtimeClientError('microphone_denied', 'Microphone permission denied');
  }
  if (browserError.name === 'NotFoundError') {
    return new RealtimeClientError('microphone_unavailable', 'No microphone is available');
  }
  if (browserError.name === 'NotReadableError') {
    return new RealtimeClientError('microphone_busy', 'The microphone is unavailable or already in use');
  }
  return browserError;
}

/**
 * Converts an OpenAI data-channel error into a bounded client error.
 *
 * The stable `realtime.provider_error` warning records only provider error
 * categories. Provider messages are intentionally excluded because they can
 * contain request details.
 *
 * @param event - Realtime server error event.
 * @returns A localized-UI-safe error with a stable category.
 */
function safeProviderError(event: RealtimeEvent): RealtimeClientError {
  const rawCode = event.error?.code || event.error?.type || 'unknown';
  const code = rawCode.replace(/[^A-Za-z0-9_.-]/g, '').slice(0, MAX_PROVIDER_ERROR_CODE_CHARS) || 'unknown';
  logger.warn('realtime.provider_error', {
    provider: 'openai',
    errorCode: code,
    errorType: event.error?.type?.slice(0, MAX_PROVIDER_ERROR_CODE_CHARS) || 'unknown',
  });
  return new RealtimeClientError('provider_error', `Realtime provider error (${code})`);
}

async function readSafeErrorBody(response: Response): Promise<string> {
  try {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const payload = await response.json() as {
        error?: { message?: string; code?: string };
        detail?: { message?: string; code?: string } | string;
      };
      if (payload.error?.message) return payload.error.message;
      if (typeof payload.detail === 'string') return payload.detail;
      if (payload.detail?.message) return payload.detail.message;
      return '';
    }
    return (await response.text()).slice(0, MAX_REALTIME_ERROR_BODY_CHARS);
  } catch {
    return '';
  }
}

async function createRealtimeSession(
  conversationId: string,
  interfaceLanguage: StartRealtimeClientOptions['interfaceLanguage'],
): Promise<RealtimeSessionResponse> {
  const response = await authenticatedFetch(API_CONFIG.realtimeSessionEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: MODEL,
      voice: 'marin',
      conversation_id: conversationId,
      interface_language: interfaceLanguage,
    }),
  });
  if (!response.ok) {
    throw new Error(realtimeFailureMessage('session', response.status, await readSafeErrorBody(response)));
  }
  const payload = await response.json() as RealtimeSessionResponse;
  if (!payload.client_secret || !payload.model) {
    throw new Error('Realtime session response is missing a client secret');
  }
  return payload;
}

async function fetchAreqaContext(
  conversationId: string,
  interfaceLanguage: StartRealtimeClientOptions['interfaceLanguage'],
  recentMessages: DisplayMessage[],
): Promise<unknown> {
  const response = await authenticatedFetch(API_CONFIG.realtimeContextEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      interface_language: interfaceLanguage,
      messages: buildRealtimeContext(recentMessages).map(({ role, content }) => ({ role, content })),
    }),
  });
  if (!response.ok) {
    return { error: 'context_unavailable' };
  }
  return response.json();
}

/**
 * Serializes user-visible message context without attachment bytes or URLs.
 *
 * @param message - Chat message owned by the bound conversation.
 * @returns Bounded text plus sanitized attachment display names.
 */
function sendRealtimeEvent(channel: RTCDataChannel, payload: unknown): void {
  if (channel.readyState === 'open') {
    channel.send(JSON.stringify(payload));
  }
}

/**
 * Resolves one context tool call and resumes the model without tools.
 *
 * @param event - Function-call completion event from the provider.
 * @param channel - Open Realtime data channel.
 * @param options - Immutable session options and current context callback.
 * @param completedToolCalls - Per-session idempotency set keyed by call id.
 * @returns A promise that settles after output delivery or duplicate suppression.
 */
async function handleToolCall(
  event: RealtimeEvent,
  channel: RTCDataChannel,
  options: StartRealtimeClientOptions,
  completedToolCalls: Set<string>,
): Promise<void> {
  const callId = event.call_id || event.item?.call_id;
  const name = event.name || event.item?.name;
  if (!callId || name !== 'get_areqa_context') return;
  if (completedToolCalls.has(callId)) {
    logger.debug('realtime.context_tool_duplicate_ignored', {
      conversationId: options.conversationId,
      callId,
    });
    return;
  }
  completedToolCalls.add(callId);

  const context = await fetchAreqaContext(
    options.getConversationId?.() || options.conversationId,
    options.interfaceLanguage,
    options.recentMessages(),
  );
  sendRealtimeEvent(channel, {
    type: 'conversation.item.create',
    item: {
      type: 'function_call_output',
      call_id: callId,
      output: JSON.stringify(context),
    },
  });
  sendRealtimeEvent(channel, {
    type: 'response.create',
    response: { tool_choice: 'none' },
  });
  logger.info('realtime.context_tool_completed', {
    conversationId: options.conversationId,
    callId,
    messageCount: options.recentMessages().length,
  });
}

function startAudioLevelMonitor(
  stream: MediaStream,
  onLevel?: (level: number) => void,
): () => void {
  if (!onLevel || typeof window === 'undefined' || !window.AudioContext) {
    return () => undefined;
  }

  let audioContext: AudioContext;
  let analyser: AnalyserNode;
  let source: MediaStreamAudioSourceNode;
  try {
    audioContext = new window.AudioContext();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.72;
    source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    if (audioContext.state === 'suspended') {
      void audioContext.resume().catch(() => undefined);
    }
  } catch {
    return () => undefined;
  }

  const samples = new Uint8Array(analyser.fftSize);
  let animationFrameId = 0;
  let smoothedLevel = 0;
  let closed = false;

  const tick = () => {
    if (closed) return;
    analyser.getByteTimeDomainData(samples);
    let sumSquares = 0;
    for (const sample of samples) {
      const centered = (sample - 128) / 128;
      sumSquares += centered * centered;
    }
    const rms = Math.sqrt(sumSquares / samples.length);
    // Gate normal room noise, then use faster attack than release so speech
    // produces a visible pulse without jitter between syllables.
    const normalizedLevel = Math.min(1, Math.max(0, rms - 0.012) * 8.5);
    const smoothing = normalizedLevel > smoothedLevel ? 0.48 : 0.18;
    smoothedLevel += (normalizedLevel - smoothedLevel) * smoothing;
    onLevel(smoothedLevel);
    animationFrameId = window.requestAnimationFrame(tick);
  };

  animationFrameId = window.requestAnimationFrame(tick);

  return () => {
    closed = true;
    if (animationFrameId) window.cancelAnimationFrame(animationFrameId);
    source.disconnect();
    analyser.disconnect();
    onLevel(0);
    void audioContext.close().catch(() => undefined);
  };
}

/**
 * Start an OpenAI Realtime WebRTC voice session.
 *
 * Args:
 *   options: UI callbacks, current conversation id, and context suppliers.
 *
 * Returns:
 *   A controller for muting local audio or disconnecting the session.
 *
 * Raises:
 *   Error through `onError` when microphone permission, session creation, SDP
 *   negotiation, or peer connection setup fails. Provider 429/401/403
 *   responses are preserved in user-visible messages so quota and access
 *   problems are diagnosable without exposing secrets.
 *
 * Side Effects:
 *   Requests microphone access before creating the OpenAI session, creates a
 *   peer connection, plays remote audio through the caller-provided stream,
 *   sends context tool outputs through the OpenAI Realtime data channel, and
 *   reports only a normalized local audio level to the UI. Microphone denial
 *   short-circuits before the backend session endpoint to avoid unnecessary
 *   upstream Realtime sessions.
 */
export async function startRealtimeClient(
  options: StartRealtimeClientOptions,
): Promise<RealtimeClientController> {
  let peerConnection: RTCPeerConnection | null = null;
  let localStream: MediaStream | null = null;
  let dataChannel: RTCDataChannel | null = null;
  let stopAudioLevelMonitor: (() => void) | null = null;
  let assistantTranscript = '';
  let assistantTranscriptFinalized = false;
  const completedToolCalls = new Set<string>();

  const cleanup = () => {
    stopAudioLevelMonitor?.();
    dataChannel?.close();
    peerConnection?.close();
    localStream?.getTracks().forEach((track) => track.stop());
    stopAudioLevelMonitor = null;
    dataChannel = null;
    peerConnection = null;
    localStream = null;
  };

  try {
    options.onStatus('connecting');
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new RealtimeClientError(
          typeof window !== 'undefined' && window.isSecureContext === false
            ? 'microphone_insecure_context'
            : 'microphone_unavailable',
          'Microphone capture is unavailable in this browser context',
        );
      }
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      throw error instanceof RealtimeClientError ? error : microphoneAccessError(error);
    }
    const session = await createRealtimeSession(options.conversationId, options.interfaceLanguage);
    stopAudioLevelMonitor = startAudioLevelMonitor(localStream, options.onInputAudioLevel);
    peerConnection = new RTCPeerConnection();
    dataChannel = peerConnection.createDataChannel('oai-events');

    peerConnection.ontrack = (event) => {
      const [remoteStream] = event.streams;
      if (remoteStream) {
        options.onRemoteStream(remoteStream);
        const stopOutputAudioLevelMonitor = startAudioLevelMonitor(remoteStream, options.onOutputAudioLevel);
        const stopInputAudioLevelMonitor = stopAudioLevelMonitor ?? (() => undefined);
        stopAudioLevelMonitor = () => {
          stopInputAudioLevelMonitor();
          stopOutputAudioLevelMonitor();
        };
      }
    };
    peerConnection.onconnectionstatechange = () => {
      if (!peerConnection) return;
      if (peerConnection.connectionState === 'connected') options.onStatus('connected');
      if (peerConnection.connectionState === 'failed') {
        options.onError(new Error('Realtime WebRTC connection failed'));
      }
    };
    localStream.getTracks().forEach((track) => {
      if (peerConnection && localStream) peerConnection.addTrack(track, localStream);
    });

    dataChannel.onopen = () => {
      const history = buildRealtimeContext(options.recentMessages());
      for (const message of history) {
        sendRealtimeEvent(dataChannel as RTCDataChannel, {
          type: 'conversation.item.create',
          item: {
            type: 'message',
            role: message.role,
            content: [{ type: message.role === 'assistant' ? 'output_text' : 'input_text', text: message.content }],
          },
        });
      }
      logger.info('realtime.history_seeded', {
        conversationId: options.getConversationId?.() || options.conversationId,
        messageCount: history.length,
      });
      options.onStatus('listening');
    };
    dataChannel.onmessage = (message) => {
      void (async () => {
        const event = JSON.parse(String(message.data)) as RealtimeEvent;
        switch (event.type) {
          case 'input_audio_buffer.speech_started':
            options.onPlaybackState?.('interrupted');
            options.onStatus('listening');
            break;
          case 'input_audio_buffer.committed':
            if (event.item_id) options.onUserTurnCommitted?.(event.item_id);
            break;
          case 'response.created':
            options.onAssistantResponseStarted?.();
            assistantTranscript = '';
            assistantTranscriptFinalized = false;
            options.onStatus('thinking');
            break;
          case 'response.audio.delta':
            options.onStatus('speaking');
            break;
          case 'output_audio_buffer.started':
            options.onPlaybackState?.('started');
            options.onStatus('speaking');
            break;
          case 'output_audio_buffer.stopped':
            options.onPlaybackState?.('stopped');
            options.onStatus('listening');
            break;
          case 'output_audio_buffer.cleared':
            options.onPlaybackState?.('interrupted');
            break;
          case 'conversation.item.input_audio_transcription.completed':
            if (event.transcript?.trim()) options.onUserTranscript(event.transcript.trim(), event.item_id);
            break;
          case 'response.audio_transcript.delta':
          case 'response.output_audio_transcript.delta':
          case 'response.text.delta':
          case 'response.output_text.delta':
            if (event.delta) {
              assistantTranscript += event.delta;
              options.onAssistantTranscriptDelta(event.delta);
            }
            break;
          case 'response.audio_transcript.done':
          case 'response.output_audio_transcript.done':
          case 'response.text.done':
          case 'response.output_text.done': {
            const finalizedTranscript = event.transcript?.trim()
              || event.text?.trim()
              || assistantTranscript.trim();
            if (!assistantTranscriptFinalized && finalizedTranscript) {
              options.onAssistantTranscriptDone(finalizedTranscript);
              assistantTranscript = '';
              assistantTranscriptFinalized = true;
            }
            break;
          }
          case 'response.done': {
            const completedTranscript = completedResponseTranscript(event);
            if (!assistantTranscriptFinalized && (completedTranscript || assistantTranscript.trim())) {
              options.onAssistantTranscriptDone(completedTranscript || assistantTranscript.trim());
              assistantTranscript = '';
              assistantTranscriptFinalized = true;
            }
            break;
          }
          case 'response.function_call_arguments.done':
          case 'response.output_item.done':
            await handleToolCall(event, dataChannel as RTCDataChannel, options, completedToolCalls);
            break;
          case 'error':
            options.onError(safeProviderError(event));
            break;
        }
      })().catch((error) => {
        options.onError(error instanceof Error ? error : new Error(String(error)));
      });
    };

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    const sdpResponse = await fetch(`${OPENAI_REALTIME_CALLS_URL}?model=${encodeURIComponent(session.model)}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.client_secret}`,
        'Content-Type': 'application/sdp',
      },
      body: offer.sdp,
    });
    if (!sdpResponse.ok) {
      throw new Error(realtimeFailureMessage('sdp', sdpResponse.status, await readSafeErrorBody(sdpResponse)));
    }
    const answerSdp = await sdpResponse.text();
    await peerConnection.setRemoteDescription({ type: 'answer', sdp: answerSdp });

    return {
      setMuted: (muted: boolean) => {
        localStream?.getAudioTracks().forEach((track) => {
          track.enabled = !muted;
        });
      },
      disconnect: cleanup,
    };
  } catch (error) {
    cleanup();
    options.onError(error instanceof Error ? error : new Error(String(error)));
    return {
      setMuted: () => undefined,
      disconnect: () => undefined,
    };
  }
}
