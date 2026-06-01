/**
 * ThinkTagParser
 * Parses streaming content and separates <think> tags from regular content
 *
 * Security Note:
 * This parser handles raw text content from the API. The output should be
 * rendered as plain text (not HTML) in the UI layer. If using dangerouslySetInnerHTML
 * or similar, ensure proper sanitization with DOMPurify or similar library.
 */

import { PARSER_CONFIG } from '@/config/api';
import type { ParsedChunk } from './types';

/**
 * Parser for handling <think> tags in streamed content
 * Maintains state across multiple parse() calls for handling split tags
 *
 * Features:
 * - Handles tags split across multiple chunks
 * - Buffer size limits to prevent memory exhaustion
 * - Graceful handling of malformed content
 */
export class ThinkTagParser {
  /** Tag constants for clarity */
  private static readonly THINK_OPEN = PARSER_CONFIG.tags.open;
  private static readonly THINK_CLOSE = PARSER_CONFIG.tags.close;
  private static readonly THINK_OPEN_LEN = PARSER_CONFIG.tags.openLength;
  private static readonly THINK_CLOSE_LEN = PARSER_CONFIG.tags.closeLength;

  /** Whether currently inside a <think> tag */
  private isInThinkTag = false;
  /** Buffer for accumulating partial content */
  private buffer = '';
  /** Track if we've warned about buffer overflow */
  private hasWarnedOverflow = false;

  /**
   * Parse incoming text and return parsed chunks
   * Handles tags that may be split across multiple calls
   * @param text - New text to parse
   * @returns Array of parsed chunks
   */
  parse(text: string): ParsedChunk[] {
    const chunks: ParsedChunk[] = [];
    this.buffer += text;

    // Guard against unbounded buffer growth (security measure)
    if (this.buffer.length > PARSER_CONFIG.maxBufferSize) {
      if (!this.hasWarnedOverflow) {
        console.warn(
          '[ThinkTagParser] Buffer exceeded maximum size, forcing flush. ' +
            'This may indicate malformed content or missing closing tags.'
        );
        this.hasWarnedOverflow = true;
      }

      // Flush buffer as current content type and reset
      if (this.isInThinkTag) {
        chunks.push({ type: 'thinking_content', content: this.buffer });
        chunks.push({ type: 'thinking_end' });
      } else {
        chunks.push({ type: 'content', content: this.buffer });
      }
      this.reset();
      return chunks;
    }

    // Process buffer for complete tags
    while (this.buffer.length > 0) {
      if (!this.isInThinkTag) {
        // Looking for <think> start tag
        const thinkStartIndex = this.buffer.indexOf(ThinkTagParser.THINK_OPEN);

        if (thinkStartIndex === -1) {
          // No <think> tag found
          // Check if buffer might contain partial tag
          const partialTagIndex = this.buffer.lastIndexOf('<');
          if (
            partialTagIndex !== -1 &&
            partialTagIndex > this.buffer.length - ThinkTagParser.THINK_OPEN_LEN
          ) {
            // Check if partial is within reasonable size (not just random '<')
            const potentialPartial = this.buffer.slice(partialTagIndex);
            if (potentialPartial.length <= PARSER_CONFIG.maxPartialTagSize) {
              // Potential partial tag at end, keep it in buffer
              const content = this.buffer.slice(0, partialTagIndex);
              if (content) {
                chunks.push({ type: 'content', content });
              }
              this.buffer = potentialPartial;
              break;
            }
          }

          // No partial tag or partial too long, output all as content
          if (this.buffer) {
            chunks.push({ type: 'content', content: this.buffer });
          }
          this.buffer = '';
          break;
        } else {
          // Found <think> tag
          // Output any content before the tag
          if (thinkStartIndex > 0) {
            const beforeContent = this.buffer.slice(0, thinkStartIndex);
            if (beforeContent) {
              chunks.push({ type: 'content', content: beforeContent });
            }
          }

          chunks.push({ type: 'thinking_start' });
          this.isInThinkTag = true;
          this.buffer = this.buffer.slice(thinkStartIndex + ThinkTagParser.THINK_OPEN_LEN);
        }
      } else {
        // Inside <think> tag, looking for </think> end tag
        const thinkEndIndex = this.buffer.indexOf(ThinkTagParser.THINK_CLOSE);

        if (thinkEndIndex === -1) {
          // No end tag found
          // Check if buffer might contain partial end tag
          const partialTagIndex = this.buffer.lastIndexOf('<');
          if (
            partialTagIndex !== -1 &&
            partialTagIndex > this.buffer.length - ThinkTagParser.THINK_CLOSE_LEN
          ) {
            // Check if partial is within reasonable size
            const potentialPartial = this.buffer.slice(partialTagIndex);
            if (potentialPartial.length <= PARSER_CONFIG.maxPartialTagSize) {
              // Potential partial end tag, keep it in buffer
              const thinkingContent = this.buffer.slice(0, partialTagIndex);
              if (thinkingContent) {
                chunks.push({ type: 'thinking_content', content: thinkingContent });
              }
              this.buffer = potentialPartial;
              break;
            }
          }

          // No partial tag or partial too long, output all as thinking content
          if (this.buffer) {
            chunks.push({ type: 'thinking_content', content: this.buffer });
          }
          this.buffer = '';
          break;
        } else {
          // Found </think> end tag
          // Output thinking content before the end tag
          if (thinkEndIndex > 0) {
            const thinkingContent = this.buffer.slice(0, thinkEndIndex);
            if (thinkingContent) {
              chunks.push({ type: 'thinking_content', content: thinkingContent });
            }
          }

          chunks.push({ type: 'thinking_end' });
          this.isInThinkTag = false;
          this.buffer = this.buffer.slice(thinkEndIndex + ThinkTagParser.THINK_CLOSE_LEN);
        }
      }
    }

    return chunks;
  }

  /**
   * Reset parser state
   * Call this when starting a new conversation/message
   */
  reset(): void {
    this.isInThinkTag = false;
    this.buffer = '';
    this.hasWarnedOverflow = false;
  }

  /**
   * Check if currently inside a think tag
   */
  get isThinking(): boolean {
    return this.isInThinkTag;
  }

  /**
   * Get current buffer contents (for debugging)
   */
  get currentBuffer(): string {
    return this.buffer;
  }

  /**
   * Get current buffer size (for monitoring)
   */
  get bufferSize(): number {
    return this.buffer.length;
  }
}
