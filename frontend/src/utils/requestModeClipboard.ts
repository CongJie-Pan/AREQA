/**
 * Round-trip a question's modes through the clipboard, like ChatGPT: copying a
 * sent bubble with "Create Image" and pasting it into the composer restores the
 * mode as well as the text.
 *
 * Mode tokens in a bubble carry `data-areqa-mode`. Both the copy button (which
 * writes text/html) and a manual selection (the browser copies the tokens'
 * HTML) bring that marker along; plain text stays just the question.
 */
import type { RequestMode } from '@/database/schema';

export const REQUEST_MODE_ATTRIBUTE = 'data-areqa-mode';

const KNOWN_MODES: ReadonlySet<RequestMode> = new Set(['create_image', 'english_tutor']);
/** Token labels a manual selection puts at the start of the plain text. */
const TOKEN_LABEL_PREFIX = /^(?:[\s ]*(?:Create Image|English Tutor)[\s ]*)+/i;

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** HTML clipboard payload for a question sent with modes. */
export function requestModesClipboardHtml(modes: RequestMode[], labels: Record<RequestMode, string>, text: string): string {
  const tokens = modes.map((mode) => `<span ${REQUEST_MODE_ATTRIBUTE}="${mode}">${escapeHtml(labels[mode])}</span>`).join(' ');
  return `${tokens} <span>${escapeHtml(text).replace(/\n/g, '<br>')}</span>`;
}

/**
 * Read modes from a paste. Returns null when the clipboard holds no AREQA mode
 * markers, so ordinary pastes keep the browser's default behaviour.
 */
export function readRequestModesFromClipboard(
  data: Pick<DataTransfer, 'getData'> | null | undefined,
): { modes: RequestMode[]; text: string } | null {
  if (!data) return null;
  const html = data.getData('text/html');
  if (!html || !html.includes(REQUEST_MODE_ATTRIBUTE)) return null;

  const document = new DOMParser().parseFromString(html, 'text/html');
  const modes = [...document.querySelectorAll(`[${REQUEST_MODE_ATTRIBUTE}]`)]
    .map((element) => element.getAttribute(REQUEST_MODE_ATTRIBUTE) as RequestMode)
    .filter((mode, index, all) => KNOWN_MODES.has(mode) && all.indexOf(mode) === index);
  if (modes.length === 0) return null;

  document.querySelectorAll(`[${REQUEST_MODE_ATTRIBUTE}]`).forEach((element) => element.remove());
  // Plain text keeps line breaks; fall back to the HTML text if it is missing.
  const plain = data.getData('text/plain') || document.body.textContent || '';
  return { modes, text: plain.replace(TOKEN_LABEL_PREFIX, '') };
}
