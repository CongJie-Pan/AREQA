/** Shared, bounded conversation snapshot for native history and context tools. */
import type { DisplayMessage } from '@/store/chat';

const MAX_MESSAGES = 24;
const MAX_MESSAGE_CHARS = 6000;
const MAX_CONTEXT_CHARS = 48000;

/**
 * Select context chronologically, retaining the topic and attachment discussion.
 *
 * Args:
 *   messages: Messages from the session's bound conversation only.
 * Returns:
 *   Role-preserving text with explicit truncation and attachment limitations.
 *   Binary data, private metadata, and attachment URLs are never included.
 */
export function buildRealtimeContext(messages: DisplayMessage[]) {
  const eligible = messages.filter((message) =>
    (message.role === 'user' || message.role === 'assistant')
    && !message.isStreaming && (message.content.trim() || message.attachments?.length));
  const anchors = new Set<number>();
  if (eligible.length) anchors.add(0);
  eligible.forEach((message, index) => {
    if (message.attachments?.length) {
      anchors.add(index);
      if (index + 1 < eligible.length) anchors.add(index + 1);
    }
  });
  const selected = new Set([...anchors].slice(-6));
  for (let index = eligible.length - 1; index >= 0 && selected.size < MAX_MESSAGES; index -= 1) {
    selected.add(index);
  }
  let remaining = MAX_CONTEXT_CHARS;
  // Budget recent turns first, then restore conversational order.
  return [...selected].sort((a, b) => b - a).flatMap((index, position) => {
    if (remaining < 200) return [];
    const message = eligible[index];
    const names = message.attachments?.slice(0, 4).map((attachment) => attachment.name.slice(0, 160));
    const suffix = names?.length
      ? `\n[Attachments: ${names.join(', ')}. Names only; file contents are not available in this snapshot.]`
      : '';
    const limit = Math.min(MAX_MESSAGE_CHARS, Math.floor(remaining / (selected.size - position))) - suffix.length;
    const content = message.content.length > limit
      ? `${message.content.slice(0, Math.floor(limit / 2) - 20)}\n[... excerpt omitted ...]\n${message.content.slice(-Math.floor(limit / 2) + 20)}`
      : message.content;
    remaining -= content.length + suffix.length;
    return [{ id: message.id, role: message.role, content: content + suffix }];
  }).reverse();
}
