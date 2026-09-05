/**
 * Speech-to-text client for the composer microphone control.
 *
 * This is intentionally separate from Live Tutor Realtime voice. It records a
 * short user utterance, asks the backend to transcribe it, and inserts the
 * resulting text into the normal message composer.
 */

import { API_CONFIG } from '@/config/api';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import type { InterfaceLanguage } from '@/contexts/UserPreferencesContext';

interface SpeechTranscriptionResponse {
  text?: string;
}

/**
 * Transcribe a browser-recorded speech clip with the backend OpenAI key.
 *
 * @param audio - Browser MediaRecorder output.
 * @param language - Current interface language used for transcription hints.
 * @returns Trimmed transcript text.
 */
export async function transcribeSpeech(audio: Blob, language: InterfaceLanguage): Promise<string> {
  const formData = new FormData();
  formData.append('file', audio, 'speech.webm');
  formData.append('interface_language', language);

  const response = await authenticatedFetch(API_CONFIG.speechTranscriptionEndpoint, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error('Speech transcription failed');
  }

  const payload = await response.json() as SpeechTranscriptionResponse;
  return (payload.text || '').trim();
}
