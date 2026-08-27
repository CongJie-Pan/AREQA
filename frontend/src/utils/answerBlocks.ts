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
