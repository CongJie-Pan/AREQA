import { describe, expect, it } from 'vitest';
import { formatSourcesForMarkdown } from '@/utils/exportChat';

describe('formatSourcesForMarkdown', () => {
  it('preserves source titles and URLs in exported transcripts', () => {
    const output = formatSourcesForMarkdown({
      id: 'message-1',
      conversationId: 'conversation-1',
      role: 'assistant',
      content: 'answer',
      timestamp: Date.now(),
      sources: [{
        title: 'NASA',
        snippet: 'source text',
        chunk_id: 'https://www.nasa.gov/example',
        url: 'https://www.nasa.gov/example',
      }],
    } as never);

    expect(output).toContain('[NASA](https://www.nasa.gov/example)');
  });
});
