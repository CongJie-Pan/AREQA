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

const OPENAI_REALTIME_CALLS_URL = 'https://api.openai.com/v1/realtime/calls';
const MODEL = 'gpt-realtime-2.1-mini';
const MAX_REALTIME_ERROR_BODY_CHARS = 500;

export type RealtimeStatus =
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'error';

export interface StartRealtimeClientOptions {
  conversationId: string;
  interfaceLanguage: 'zh-TW' | 'zh-CN' | 'en';
  recentMessages: () => DisplayMessage[];
  onRemoteStream: (stream: MediaStream) => void;
  onInputAudioLevel?: (level: number) => void;
  onStatus: (status: RealtimeStatus) => void;
  onAssistantResponseStarted?: () => void;
  onUserTranscript: (transcript: string) => void;
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
  transcript?: string;
  delta?: string;
  call_id?: string;
  name?: string;
  arguments?: string;
  item?: {
    type?: string;
    call_id?: string;
    name?: string;
    arguments?: string;
  };
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

function microphonePermissionMessage(error: unknown): Error {
  const browserError = error instanceof Error ? error : new Error(String(error));
  if (
    browserError.name === 'NotAllowedError'
    || browserError.name === 'SecurityError'
    || browserError.message.toLowerCase().includes('permission')
  ) {
    return new Error('Microphone permission denied');
  }
  return browserError;
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
      messages: recentMessages
        .filter((message) => message.role === 'user' || message.role === 'assistant')
        .slice(-12)
        .map((message) => ({
          role: message.role,
          content: message.content.slice(0, 1200),
        })),
    }),
  });
  if (!response.ok) {
    return { error: 'context_unavailable' };
  }
  return response.json();
}

function sendRealtimeEvent(channel: RTCDataChannel, payload: unknown): void {
  if (channel.readyState === 'open') {
    channel.send(JSON.stringify(payload));
  }
}

async function handleToolCall(
  event: RealtimeEvent,
  channel: RTCDataChannel,
  options: StartRealtimeClientOptions,
): Promise<void> {
  const callId = event.call_id || event.item?.call_id;
  const name = event.name || event.item?.name;
  if (!callId || name !== 'get_areqa_context') return;

  const context = await fetchAreqaContext(
    options.conversationId,
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
  sendRealtimeEvent(channel, { type: 'response.create' });
}

function startInputAudioLevelMonitor(
  stream: MediaStream,
  onLevel?: StartRealtimeClientOptions['onInputAudioLevel'],
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
    const normalizedLevel = Math.min(1, rms * 3.6);
    smoothedLevel = smoothedLevel * 0.82 + normalizedLevel * 0.18;
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
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      throw microphonePermissionMessage(error);
    }
    const session = await createRealtimeSession(options.conversationId, options.interfaceLanguage);
    stopAudioLevelMonitor = startInputAudioLevelMonitor(localStream, options.onInputAudioLevel);
    peerConnection = new RTCPeerConnection();
    dataChannel = peerConnection.createDataChannel('oai-events');

    peerConnection.ontrack = (event) => {
      const [remoteStream] = event.streams;
      if (remoteStream) options.onRemoteStream(remoteStream);
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
      options.onStatus('listening');
    };
    dataChannel.onmessage = (message) => {
      void (async () => {
        const event = JSON.parse(String(message.data)) as RealtimeEvent;
        switch (event.type) {
          case 'input_audio_buffer.speech_started':
            options.onAssistantResponseStarted?.();
            options.onStatus('listening');
            break;
          case 'response.created':
            options.onAssistantResponseStarted?.();
            assistantTranscript = '';
            options.onStatus('thinking');
            break;
          case 'response.audio.delta':
            options.onStatus('speaking');
            break;
          case 'conversation.item.input_audio_transcription.completed':
            if (event.transcript?.trim()) options.onUserTranscript(event.transcript.trim());
            break;
          case 'response.audio_transcript.delta':
          case 'response.output_text.delta':
            if (event.delta) {
              assistantTranscript += event.delta;
              options.onAssistantTranscriptDelta(event.delta);
            }
            break;
          case 'response.audio_transcript.done':
          case 'response.output_text.done':
            if (assistantTranscript.trim()) {
              options.onAssistantTranscriptDone(event.transcript?.trim() || assistantTranscript.trim());
              assistantTranscript = '';
            }
            break;
          case 'response.function_call_arguments.done':
          case 'response.output_item.done':
            await handleToolCall(event, dataChannel as RTCDataChannel, options);
            break;
          case 'error':
            options.onError(new Error('Realtime provider returned an error'));
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
