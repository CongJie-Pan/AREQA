/** Script normalization for speech transcripts, without translating languages. */
import { Converter } from 'opencc-js/cn2t';

const toTraditional = Converter({ from: 'cn', to: 'tw' });

/**
 * Normalize Chinese speech text before it enters the authoritative chat flow.
 *
 * Args:
 *   text: Provider speech transcript (never typed source code or chat input).
 *   language: Interface preference. Simplified Chinese UI preserves provider
 *     script; all other UI languages convert Chinese speech to Taiwan
 *     Traditional Chinese while leaving non-Chinese text unchanged.
 *
 * Returns:
 *   A script-normalized transcript for chat storage and backend language
 *   detection.
 */
export function normalizeVoiceTranscript(text: string, language: string): string {
  return language === 'zh-CN' ? text : toTraditional(text);
}
