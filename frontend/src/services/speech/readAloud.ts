/**
 * Text-to-speech client for assistant reply read-out.
 */

import { API_CONFIG } from '@/config/api';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { normalizeReadbackText } from '@/services/realtime/readbackText';

export function prepareReadAloudText(markdown: string): string {
  return normalizeReadbackText(markdown);
}

export async function createReadAloudAudio(markdown: string, signal?: AbortSignal): Promise<Blob> {
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

  return response.blob();
}
