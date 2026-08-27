import type { AnswerBlock } from '@/database/schema';

/**
 * Return answer blocks that are safe to write to durable stores.
 *
 * PDF attachment image blocks contain data URIs derived from uploaded files.
 * They are useful for the live turn but should not be written to Supabase,
 * local sync payloads, or shared conversations. Paragraph blocks and normal
 * provider image blocks remain persistent.
 */
export function persistentAnswerBlocks(blocks: AnswerBlock[] | undefined): AnswerBlock[] | undefined {
  if (!blocks || blocks.length === 0) return undefined;
  const persistentBlocks = blocks.filter((block) => !(block.type === 'image_block' && block.transient));
  return persistentBlocks.length > 0 ? persistentBlocks : undefined;
}
