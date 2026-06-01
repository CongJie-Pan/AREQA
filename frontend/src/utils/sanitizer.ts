export type Message = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

/**
 * Removes <think>...</think> blocks from ALL message roles before sending to backend.
 * Applies to assistants (reasoning traces) and user messages alike, to save tokens.
 * After block removal, collapses consecutive spaces so adjacent removals don't
 * leave double gaps (e.g. "Text  More text." → "Text More text.").
 */
export function sanitizeMessagesForAPI(messages: Message[]): Message[] {
  return messages.map(msg => {
    let content = msg.content;

    // Remove complete <think>...</think> blocks (non-greedy, handles multiline)
    content = content.replace(/<think>[\s\S]*?<\/think>/g, '');

    // Match unclosed think block at the end
    content = content.replace(/<think>[\s\S]*$/, '');

    // Collapse multiple consecutive spaces/tabs into a single space
    // (prevents double gaps when two adjacent blocks are removed)
    content = content.replace(/[ \t]{2,}/g, ' ');

    return {
      ...msg,
      content: content.trim()
    };
  });
}
