/**
 * Live Tutor store type definitions.
 *
 * The voice MVP keeps realtime connection state separate from the text chat
 * stream so WebRTC lifecycle changes cannot corrupt the established SSE chat
 * contract.
 */

export type LiveTutorStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'muted'
  | 'error';

export interface LiveTutorState {
  isOpen: boolean;
  status: LiveTutorStatus;
  isMuted: boolean;
  avatarEnabled: boolean;
  closeRequestId: number;
  userTranscript: string;
  assistantTranscript: string;
  error: string | null;
  sendVoiceMessage: ((content: string, files: File[]) => Promise<{ completed: boolean }>) | null;
}

export interface LiveTutorActions {
  open: () => void;
  close: () => void;
  requestClose: () => void;
  setStatus: (status: LiveTutorStatus) => void;
  setMuted: (isMuted: boolean) => void;
  setAvatarEnabled: (enabled: boolean) => void;
  setUserTranscript: (transcript: string) => void;
  setAssistantTranscript: (transcript: string) => void;
  appendAssistantTranscript: (delta: string) => void;
  setError: (error: string | null) => void;
  resetTranscript: () => void;
  setSendVoiceMessage: (handler: LiveTutorState['sendVoiceMessage']) => void;
}

export type LiveTutorStore = LiveTutorState & LiveTutorActions;
