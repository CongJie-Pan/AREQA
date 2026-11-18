/**
 * Topic Finder (選題) topic card client.
 *
 * The card lives server-side; the browser reads it, adopts drafts, and picks
 * stages through the Next.js proxy. The AI can only propose a pending draft,
 * which is adopted only for the version the learner is looking at. Only the
 * learner moves between stages, in any order.
 */

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';

export const TOPIC_CARD_COMPLETED_STAGE = 6;

export interface TopicCardContent {
  pain_point: string;
  mother_question: string;
  candidates: string[];
  operationalization: { term: string; measure: string }[];
  /** Stage-5 checks; older cards may not have it. */
  feasibility?: TopicFeasibilityItem[];
  discarded: { topic: string; filter: number; reason: string; can_return: boolean }[];
  objections: string[];
}

export type TopicFeasibilityKey = 'time' | 'data' | 'advisor' | 'prior_work';
export const TOPIC_FEASIBILITY_KEYS: TopicFeasibilityKey[] = ['time', 'data', 'advisor', 'prior_work'];

export interface TopicFeasibilityItem {
  key: TopicFeasibilityKey;
  status: 'ok' | 'unsure' | 'blocked';
  note: string;
}

/** AI search hints; reference only, never the learner's decisions. */
export interface TopicCardSuggestions {
  keywords: string[];
  gaps: string[];
  related: string[];
}

export interface TopicCardState {
  stage: number;
  version: number;
  card: TopicCardContent;
  pending: { card: TopicCardContent; notes: string[] } | null;
  suggestions?: TopicCardSuggestions;
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

/** Adopt the AI draft for the version the learner saw; the stage does not change. */
export async function adoptTopicCardDraft(
  conversationId: string,
  version: number,
): Promise<{ state: TopicCardState; adopted: boolean }> {
  const response = await authenticatedFetch(`/api/research-coach/${encodeURIComponent(conversationId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version }),
  });
  if (!response.ok) {
    logger.info('topic_card_adopt_failed', { conversationId, status: response.status });
    throw new TopicCardError(failureFor(response.status));
  }
  const result = (await response.json()) as { state: TopicCardState; adopted: boolean };
  logger.info('topic_card_adopted', {
    conversationId, adopted: result.adopted, stage: result.state.stage, version: result.state.version,
  });
  return result;
}

/** Move to the stage the learner picked (1-5, or 6 for done). */
export async function setTopicCardStage(conversationId: string, stage: number): Promise<TopicCardState> {
  const response = await authenticatedFetch(`/api/research-coach/${encodeURIComponent(conversationId)}/stage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stage }),
  });
  if (!response.ok) {
    logger.info('topic_card_stage_failed', { conversationId, status: response.status });
    throw new TopicCardError(failureFor(response.status));
  }
  const state = (await response.json()) as TopicCardState;
  logger.info('topic_card_stage_set', { conversationId, stage: state.stage, version: state.version });
  return state;
}

/** The draft when the AI proposed one, otherwise the last confirmed card. */
export function visibleCard(state: TopicCardState): TopicCardContent {
  return state.pending?.card ?? state.card;
}
