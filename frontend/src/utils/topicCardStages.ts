/**
 * Topic Finder stages in plain language, shared by the topic card, the header
 * badge, the tour, and the Markdown export.
 *
 * Stages 1-5 each have a one-line goal and a subtitle; 6 means the learner has
 * been through all five. Learners may jump between stages.
 */

import type { TranslationKey } from '@/contexts/UserPreferencesContext';
import { TOPIC_CARD_COMPLETED_STAGE } from '@/services/topicCard';

type Translate = (key: TranslationKey, params?: Record<string, string | number>) => string;

export const TOPIC_STEP_COUNT = 5;
export const TOPIC_FIRST_STAGE = 1;

export const TOPIC_STAGE_TITLE_KEYS: TranslationKey[] = [
  'topicStageTitle1', 'topicStageTitle2', 'topicStageTitle3', 'topicStageTitle4', 'topicStageTitle5',
];

const TOPIC_STAGE_SUB_KEYS: TranslationKey[] = [
  'topicStageSub1', 'topicStageSub2', 'topicStageSub3', 'topicStageSub4', 'topicStageSub5',
];

/** A field opens at the stage that asks about it (mirrors the backend limits). */
export const MOTHER_QUESTION_STAGE = 3;
export const OPERATIONALIZATION_STAGE = 4;
export const FEASIBILITY_STAGE = 5;

/** Stored zeros come from cards saved before stage 0 was folded into stage 1. */
export function normalizeTopicStage(stage: number): number {
  return Math.min(Math.max(Math.trunc(stage) || TOPIC_FIRST_STAGE, TOPIC_FIRST_STAGE), TOPIC_CARD_COMPLETED_STAGE);
}

/** "第 3 階段" or "完成". */
export function topicCardStageLabel(t: Translate, stage: number): string {
  const current = normalizeTopicStage(stage);
  if (current >= TOPIC_CARD_COMPLETED_STAGE) return t('topicCardStageDone');
  return t('topicCardStageFilter', { n: current });
}

/** The stage's one-line goal. */
export function topicStageTitle(t: Translate, stage: number): string {
  const current = normalizeTopicStage(stage);
  if (current >= TOPIC_CARD_COMPLETED_STAGE) return t('topicCardDone');
  return t(TOPIC_STAGE_TITLE_KEYS[current - 1]);
}

/** The stage's subtitle: what to do there. */
export function topicStageSubtitle(t: Translate, stage: number): string {
  const current = normalizeTopicStage(stage);
  if (current >= TOPIC_CARD_COMPLETED_STAGE) return t('topicCardDoneSub');
  return t(TOPIC_STAGE_SUB_KEYS[current - 1]);
}
