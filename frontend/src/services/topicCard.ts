/**
 * Topic Finder (選題) topic card client.
 *
 * The card lives server-side; the browser reads it and confirms stages through
 * the Next.js proxy. The AI can only propose a pending draft; a stage advances
 * only when the learner confirms the version they are looking at.
 */

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';

export const TOPIC_CARD_COMPLETED_STAGE = 6;

export interface TopicCardContent {
  pain_point: string;
  mother_question: string;
  candidates: string[];
  operationalization: { term: string; measure: string }[];
  discarded: { topic: string; filter: number; reason: string; can_return: boolean }[];
  objections: string[];
}

export interface TopicCardState {
  stage: number;
  version: number;
  card: TopicCardContent;
  pending: { card: TopicCardContent; notes: string[] } | null;
  history: { version: number; stage: number; note: string; confirmed_at: number }[];
}

/** `not_synced`: the conversation has not reached the cloud yet (or is not the user's). */
export type TopicCardFailure = 'not_synced' | 'unavailable';

export class TopicCardError extends Error {
  constructor(public readonly reason: TopicCardFailure) {
    super(reason);
    this.name = 'TopicCardError';
  }
}

function failureFor(status: number): TopicCardFailure {
  return status === 404 ? 'not_synced' : 'unavailable';
}

export async function fetchTopicCard(conversationId: string, signal?: AbortSignal): Promise<TopicCardState> {
  const response = await authenticatedFetch(`/api/research-coach/${encodeURIComponent(conversationId)}/card`, {
    cache: 'no-store',
    signal,
  });
  if (!response.ok) {
    logger.info('topic_card_load_failed', { conversationId, status: response.status });
    throw new TopicCardError(failureFor(response.status));
  }
  return (await response.json()) as TopicCardState;
}

export async function confirmTopicCardStage(
  conversationId: string,
  version: number,
): Promise<{ state: TopicCardState; advanced: boolean }> {
  const response = await authenticatedFetch(`/api/research-coach/${encodeURIComponent(conversationId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version }),
  });
  if (!response.ok) {
    logger.info('topic_card_confirm_failed', { conversationId, status: response.status });
    throw new TopicCardError(failureFor(response.status));
  }
  const result = (await response.json()) as { state: TopicCardState; advanced: boolean };
  logger.info('topic_card_confirmed', {
    conversationId, advanced: result.advanced, stage: result.state.stage, version: result.state.version,
  });
  return result;
}

/** The draft when the AI proposed one, otherwise the last confirmed card. */
export function visibleCard(state: TopicCardState): TopicCardContent {
  return state.pending?.card ?? state.card;
}
