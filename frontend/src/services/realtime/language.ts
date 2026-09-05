/** Script normalization for speech transcripts, without translating languages. */
import { Converter } from 'opencc-js/cn2t';

const toTraditional = Converter({ from: 'cn', to: 'tw' });

/**
 * Normalize Chinese speech text to the selected script before display/storage.
 *
 * Args:
 *   text: Provider speech transcript (never typed source code or chat input).
 *   language: Interface preference; other locales preserve provider output.
 * Returns:
 *   Taiwan Traditional Chinese for zh-TW, otherwise the original transcript.
 */
export function normalizeVoiceTranscript(text: string, language: string): string {
  return language === 'zh-TW' ? toTraditional(text) : text;
}
