import type { AnswerBlock } from '@/database/schema';

/**
 * Return answer blocks that are safe to write to durable stores.
 *
 * PDF attachment image blocks stay transient only when the backend could not
 * persist them to Supabase Storage. Persisted PDF visuals arrive as signed URLs
 * without `transient`, so they can survive refreshes and conversation switches.
 */
export function persistentAnswerBlocks(blocks: AnswerBlock[] | undefined): AnswerBlock[] | undefined {
  if (!blocks || blocks.length === 0) return undefined;
  const persistentBlocks = blocks.filter((block) => !(block.type === 'image_block' && block.transient));
  return persistentBlocks.length > 0 ? persistentBlocks : undefined;
}

/**
 * Rebuild answer blocks after a user edits the Markdown body.
 *
 * Args:
 *   content: The edited Markdown content that should replace stale generated
 *     paragraph blocks.
 *   previousBlocks: Existing backend-produced answer blocks from the message
 *     or note before the edit.
 *
 * Returns:
 *   A Markdown paragraph block followed by existing image blocks, or undefined
 *   when there are no image blocks to preserve.
 *
 * Side Effects:
 *   None. The helper intentionally keeps only image blocks from the previous
 *   structured answer because old paragraph blocks no longer represent the
 *   user-edited Markdown.
 */
export function answerBlocksForEditedContent(
  content: string,
  previousBlocks: AnswerBlock[] | undefined,
): AnswerBlock[] | undefined {
  const imageBlocks = (previousBlocks ?? []).filter((block) => block.type === 'image_block');
  if (imageBlocks.length === 0) return undefined;

  return [
    { type: 'paragraph', text: content },
    ...imageBlocks,
  ];
}
