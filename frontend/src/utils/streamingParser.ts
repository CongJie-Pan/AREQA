export type ParseResult = {
  text: string;
  thinking: string;
  isThinking: boolean;
};

/**
 * Stateful parser for dealing with Server-Sent Events (SSE) streaming
 * where a <think> or </think> tag could be split unpredictably across chunks.
 * Example split: Chunk 1: `<thi` Chunk 2: `nk>Hello`
 */
export class StreamingParser {
  private buffer: string = '';
  private isThinkingState: boolean = false;

  public parseChunk(chunk: string): ParseResult {
    this.buffer += chunk;
    
    let textOut = '';
    let thinkOut = '';

    while (this.buffer.length > 0) {
      if (!this.isThinkingState) {
        const startIndex = this.buffer.indexOf('<think>');
        const possibleStart = this.buffer.indexOf('<');

        if (startIndex !== -1) {
          // Found opening tag
          textOut += this.buffer.substring(0, startIndex);
          this.isThinkingState = true;
          this.buffer = this.buffer.substring(startIndex + 7); // 7 is length of <think>
        } else if (possibleStart !== -1 && possibleStart > this.buffer.length - 7) {
          // It could be the start of a think tag split across chunks
          textOut += this.buffer.substring(0, possibleStart);
          this.buffer = this.buffer.substring(possibleStart);
          break; // Wait for next chunk
        } else {
          // Normal text
          textOut += this.buffer;
          this.buffer = '';
        }
      } else {
        const endIndex = this.buffer.indexOf('</think>');
        const possibleEnd = this.buffer.indexOf('<');

        if (endIndex !== -1) {
          // Found closing tag
          thinkOut += this.buffer.substring(0, endIndex);
          this.isThinkingState = false;
          this.buffer = this.buffer.substring(endIndex + 8); // 8 is length of </think>
        } else if (possibleEnd !== -1 && possibleEnd > this.buffer.length - 8) {
          // Could be the start of </think>
          thinkOut += this.buffer.substring(0, possibleEnd);
          this.buffer = this.buffer.substring(possibleEnd);
          break;
        } else {
          // Inside think block
          thinkOut += this.buffer;
          this.buffer = '';
        }
      }
    }

    return {
      text: textOut,
      thinking: thinkOut,
      isThinking: this.isThinkingState
    };
  }
}
