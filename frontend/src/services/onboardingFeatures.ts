/**
 * Find the guided-tour features an existing learner has not used yet.
 *
 * Uses only the account's local history (IndexedDB), never the server:
 * - notes: any saved note
 * - branches: any conversation created as a branch
 * - the "+" menu: any upload or generated image
 */
import { db } from '@/database/db';
import type { FeatureStepId } from '@/store/onboarding';

export async function detectUnusedFeatureSteps(userId: string): Promise<FeatureStepId[]> {
  const [noteCount, branchConversation, plusMessage] = await Promise.all([
    db.notes.where('userId').equals(userId).count(),
    db.conversations.where('userId').equals(userId).filter((conversation) => Boolean(conversation.branchOrigin)).first(),
    db.messages.where('userId').equals(userId).filter((message) => Boolean(
      message.attachments?.length
      || message.answerBlocks?.some((block) => block.type === 'image_block' && block.provider === 'generated_image'),
    )).first(),
  ]);

  const unused: FeatureStepId[] = [];
  if (noteCount === 0) unused.push('addNote');
  if (!branchConversation) unused.push('replyMore');
  if (!plusMessage) unused.push('composerPlus');
  return unused;
}
