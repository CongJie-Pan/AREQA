/**
 * Topic Finder divergence: explore one candidate topic in its own branch.
 *
 * The branch copies the conversation up to the latest finished reply, keeps the
 * Topic Finder kind, and gets its own topic card (cards are per conversation),
 * so exploring never edits the main card.
 */

import { databaseService } from '@/services/database';
import { sendMessage, switchConversation } from '@/services/chat';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { generateUUID } from '@/utils/id';
import { logger } from '@/utils/logger';

export class TopicBranchUnavailableError extends Error {
  constructor() {
    super('No finished reply to branch from');
    this.name = 'TopicBranchUnavailableError';
  }
}

export interface ExploreCandidateOptions {
  sourceConversationId: string;
  /** Branch title shown in the sidebar (bounded to 80 characters). */
  title: string;
  /** First learner message in the branch, naming the candidate. */
  firstMessage: string;
}

/** Create the branch, open it, and send its first message. Returns the branch id. */
export async function exploreCandidateInBranch({ sourceConversationId, title, firstMessage }: ExploreCandidateOptions): Promise<string> {
  const chat = useChatStore.getState();
  const anchor = chat.isStreaming ? undefined : [...chat.messages].reverse().find((entry) => (
    entry.conversationId === sourceConversationId && entry.role === 'assistant'
    && !entry.isStreaming && entry.content.trim().length > 0));
  if (!anchor) throw new TopicBranchUnavailableError();

  const branch = await databaseService.conversation.branch(sourceConversationId, anchor.id, generateUUID(), title.slice(0, 80));
  useConversationStore.setState((state) => ({
    conversations: [branch, ...state.conversations.filter((entry) => entry.id !== branch.id)],
  }));
  logger.info('topic_finder_candidate_branch_created', { sourceConversationId, branchId: branch.id, kind: branch.kind ?? 'chat' });
  await switchConversation(branch.id);
  void sendMessage(firstMessage, branch.id);
  return branch.id;
}
