/**
 * API Configuration
 * Centralized configuration for API endpoints and settings
 */

/**
 * API configuration values
 * All values can be overridden via environment variables
 */
export const API_CONFIG = {
  /**
   * Chat API endpoint
   * Default: '/api/chat' (proxied through Next.js)
   */
  chatEndpoint: process.env.NEXT_PUBLIC_CHAT_API_ENDPOINT || '/api/chat',

  /**
   * Realtime voice session endpoint.
   * Default: '/api/realtime/session' (proxied through Next.js)
   */
  realtimeSessionEndpoint: process.env.NEXT_PUBLIC_REALTIME_SESSION_ENDPOINT || '/api/realtime/session',

  /**
   * Realtime AREQA context endpoint used by the browser-side tool bridge.
   * Default: '/api/realtime/context' (proxied through Next.js)
   */
  realtimeContextEndpoint: process.env.NEXT_PUBLIC_REALTIME_CONTEXT_ENDPOINT || '/api/realtime/context',

  /**
   * LiveKit avatar session endpoint.
   * Default: '/api/realtime/livekit-avatar-session' (proxied through Next.js)
   */
  liveKitAvatarSessionEndpoint: process.env.NEXT_PUBLIC_LIVEKIT_AVATAR_SESSION_ENDPOINT
    || '/api/realtime/livekit-avatar-session',

  /**
   * Live voice transport implementation.
   * Default: 'webrtc'. Set NEXT_PUBLIC_LIVE_VOICE_TRANSPORT=websocket to opt
   * into the lower-level audio queue pipeline while keeping WebRTC as fallback.
   */
  liveVoiceTransport: process.env.NEXT_PUBLIC_LIVE_VOICE_TRANSPORT === 'websocket'
    ? 'websocket'
    : 'webrtc',

  /**
   * Speech-to-text endpoint for the composer microphone button.
   * Default: '/api/speech/transcribe' (proxied through Next.js)
   */
  speechTranscriptionEndpoint: process.env.NEXT_PUBLIC_SPEECH_TRANSCRIPTION_ENDPOINT || '/api/speech/transcribe',

  /**
   * Request timeout in milliseconds
   * Default: 30 seconds
   */
  timeout: parseInt(process.env.NEXT_PUBLIC_API_TIMEOUT || '30000', 10),

  /**
   * Maximum message content length
   * Default: 10,000 characters
   */
  maxMessageLength: parseInt(process.env.NEXT_PUBLIC_MAX_MESSAGE_LENGTH || '10000', 10),

  /**
   * Minimum message content length
   * Default: 1 character (after trim)
   */
  minMessageLength: 1,
} as const;

/**
 * Parser configuration values
 */
export const PARSER_CONFIG = {
  /**
   * Maximum buffer size in bytes before forced flush
   * Prevents memory exhaustion from malformed content
   * Default: 100KB
   */
  maxBufferSize: parseInt(process.env.NEXT_PUBLIC_PARSER_MAX_BUFFER || '102400', 10),

  /**
   * Maximum size for partial tags held in buffer
   * Default: 100 bytes
   */
  maxPartialTagSize: 100,

  /**
   * Think tag constants
   */
  tags: {
    open: '<think>',
    close: '</think>',
    openLength: 7, // '<think>'.length
    closeLength: 8, // '</think>'.length
  },
} as const;

/**
 * Validate API configuration on load
 * Logs warnings for invalid configurations
 */
export function validateApiConfig(): void {
  if (API_CONFIG.timeout < 1000) {
    console.warn('[API Config] Timeout is very short:', API_CONFIG.timeout, 'ms');
  }

  if (API_CONFIG.maxMessageLength < 100) {
    console.warn('[API Config] Max message length is very short:', API_CONFIG.maxMessageLength);
  }

  if (PARSER_CONFIG.maxBufferSize < 10000) {
    console.warn('[Parser Config] Max buffer size is very small:', PARSER_CONFIG.maxBufferSize);
  }
}
