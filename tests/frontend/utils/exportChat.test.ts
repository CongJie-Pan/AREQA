import { describe, expect, it } from 'vitest';
import { formatAnswerBlocksForMarkdown, formatSourcesForMarkdown } from '@/utils/exportChat';

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

describe('formatAnswerBlocksForMarkdown', () => {
  it('exports image block metadata and vision analysis', () => {
    const output = formatAnswerBlocksForMarkdown({
      id: 'message-1',
      conversationId: 'conversation-1',
      role: 'assistant',
      content: 'answer',
      timestamp: Date.now(),
      answerBlocks: [
        {
          type: 'image_block',
          slotId: 'img_1',
          topic: 'Forest plot',
          purpose: 'diagram',
          imageUrl: 'https://example.edu/forest.png',
          thumbnailUrl: 'https://example.edu/forest-thumb.png',
          sourceUrl: 'https://example.edu/source',
          sourceDomain: 'example.edu',
          caption: 'Annotated forest plot',
          provider: 'serpapi_images',
          license: 'unknown',
          safetyStatus: 'pass',
          matchConfidence: 0.9,
          visionSummary: 'A forest plot with confidence intervals and a summary diamond.',
          visibleElements: ['null line OR=1', '95% CI', 'summary diamond'],
          howToRead: ['Check whether confidence intervals cross the null line.'],
          visionConfidence: 'high',
          visionLimitations: ['Small text may be hard to read.'],
        },
      ],
    } as never);

    expect(output).toContain('#### 圖片資訊');
    expect(output).toContain('![Forest plot](https://example.edu/forest.png)');
    expect(output).toContain('圖像理解摘要: A forest plot');
    expect(output).toContain('null line OR=1');
    expect(output).toContain('Check whether confidence intervals cross the null line.');
    expect(output).toContain('[example.edu](https://example.edu/source)');
  });

  it('omits the image section when no image blocks are present', () => {
    const output = formatAnswerBlocksForMarkdown({
      id: 'message-1',
      conversationId: 'conversation-1',
      role: 'assistant',
      content: 'answer',
      timestamp: Date.now(),
      answerBlocks: [{ type: 'paragraph', text: 'answer' }],
    } as never);

    expect(output).toBe('');
  });
});
