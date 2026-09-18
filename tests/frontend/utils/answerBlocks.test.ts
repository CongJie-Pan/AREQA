import { describe, expect, it } from 'vitest';
import type { AnswerBlock } from '@/database/schema';
import { answerBlocksForEditedContent, persistentAnswerBlocks } from '@/utils/answerBlocks';

const baseImageBlock = {
  type: 'image_block' as const,
  slotId: 'pdf_img_1',
  topic: 'paper.pdf page 1',
  purpose: 'chart',
  imageUrl: 'https://example.supabase.co/storage/v1/object/sign/bucket/path?token=abc',
  thumbnailUrl: 'https://example.supabase.co/storage/v1/object/sign/bucket/path?token=abc',
  sourceUrl: '#pdf-attachment-page-1',
  sourceDomain: 'uploaded PDF',
  caption: 'Figure 1',
  provider: 'pdf_attachment',
  tier: 'pdf_attachment',
  license: 'user_provided_attachment',
  status: 'resolved' as const,
  safetyStatus: 'pass' as const,
  matchConfidence: 0.92,
};

describe('persistentAnswerBlocks', () => {
  it('keeps persisted PDF image blocks with signed storage URLs', () => {
    const blocks: AnswerBlock[] = [
      { type: 'paragraph', text: 'Explanation' },
      {
        ...baseImageBlock,
        storageBucket: 'areqa-pdf-visuals',
        storagePath: 'conversations/c1/pdf-visuals/pdf_img_1.png',
        storageExpiresAt: 1234567890,
      },
    ];

    expect(persistentAnswerBlocks(blocks)).toEqual(blocks);
  });

  it('filters transient PDF data URI image blocks from durable storage', () => {
    const blocks: AnswerBlock[] = [
      { type: 'paragraph', text: 'Explanation' },
      {
        ...baseImageBlock,
        imageUrl: 'data:image/png;base64,iVBORw0KGgo=',
        thumbnailUrl: 'data:image/png;base64,iVBORw0KGgo=',
        transient: true,
      },
    ];

    expect(persistentAnswerBlocks(blocks)).toEqual([{ type: 'paragraph', text: 'Explanation' }]);
  });
});

describe('answerBlocksForEditedContent', () => {
  it('replaces stale text blocks with edited Markdown and preserves image blocks', () => {
    const blocks: AnswerBlock[] = [
      { type: 'paragraph', text: 'Old explanation' },
      baseImageBlock,
    ];

    expect(answerBlocksForEditedContent('Edited **Markdown**', blocks)).toEqual([
      { type: 'paragraph', text: 'Edited **Markdown**' },
      baseImageBlock,
    ]);
  });

  it('returns undefined when there are no images to preserve', () => {
    expect(answerBlocksForEditedContent('Edited text', [{ type: 'paragraph', text: 'Old text' }])).toBeUndefined();
  });
});
