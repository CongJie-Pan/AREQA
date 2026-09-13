const MAX_BLANK_LINES = /\n{3,}/g;
const MARKDOWN_LINK = /\[([^\]]+)\]\(([^)]+)\)/g;
const MARKDOWN_IMAGE = /!\[([^\]]*)\]\(([^)]+)\)/g;
const FENCED_CODE_MARKER = /^\s*```[\w-]*\s*$/gm;
const HEADING_MARKER = /^#{1,6}\s+/gm;
const BLOCKQUOTE_MARKER = /^>\s?/gm;
const LIST_MARKER = /^\s*(?:[-*+]|\d+[.)])\s+/gm;
const HORIZONTAL_RULE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm;
const STRONG_MARKER = /(\*\*|__)/g;
const ASTERISK_EMPHASIS = /\*([^*\n]+)\*/g;
const INLINE_CODE_MARKER = /`([^`]+)`/g;
const MATH_MARKER = /\$([^$\n]+)\$/g;
const HTML_TAG = /<[^>]+>/g;
const EXTENDED_PICTOGRAPHIC = /\p{Extended_Pictographic}/gu;

/**
 * Converts an AREQA markdown answer into one deterministic live readback text.
 *
 * The result is intentionally used for both the visible live voice answer and
 * speech playback so the learner never sees one answer while hearing another.
 */
export function normalizeReadbackText(markdown: string): string {
  return markdown
    .replace(/\r\n?/g, '\n')
    .replace(MARKDOWN_IMAGE, '$1')
    .replace(MARKDOWN_LINK, '$1')
    .replace(FENCED_CODE_MARKER, '')
    .replace(HORIZONTAL_RULE, '')
    .replace(HEADING_MARKER, '')
    .replace(BLOCKQUOTE_MARKER, '')
    .replace(LIST_MARKER, '')
    .replace(INLINE_CODE_MARKER, '$1')
    .replace(MATH_MARKER, '$1')
    .replace(STRONG_MARKER, '')
    .replace(ASTERISK_EMPHASIS, '$1')
    .replace(HTML_TAG, '')
    .replace(EXTENDED_PICTOGRAPHIC, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]+/g, '\n')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(MAX_BLANK_LINES, '\n\n')
    .trim();
}
