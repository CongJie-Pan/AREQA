/**
 * Topic Finder steps in plain language, shared by the topic card, the header
 * badge, the tour, and the Markdown export.
 *
 * Step 0 is the starting point (the learner's pain point); steps 1-5 each ask
 * one question; 6 means the learner confirmed all five.
 */

import type { TranslationKey } from '@/contexts/UserPreferencesContext';
import { TOPIC_CARD_COMPLETED_STAGE } from '@/services/topicCard';

type Translate = (key: TranslationKey, params?: Record<string, string | number>) => string;

export const TOPIC_STEP_COUNT = 5;

export const TOPIC_STAGE_QUESTION_KEYS: TranslationKey[] = [
  'topicStageQ0', 'topicStageQ1', 'topicStageQ2', 'topicStageQ3', 'topicStageQ4', 'topicStageQ5',
];

export const TOPIC_STAGE_WHY_KEYS: TranslationKey[] = [
  'topicStageWhy0', 'topicStageWhy1', 'topicStageWhy2', 'topicStageWhy3', 'topicStageWhy4', 'topicStageWhy5',
];

/** The step's field opens when the learner reaches it (mirrors the backend limits). */
export const MOTHER_QUESTION_STAGE = 3;
export const OPERATIONALIZATION_STAGE = 4;

/** "起點", "第 3 關／共 5 關", or "完成". */
export function topicCardStageLabel(t: Translate, stage: number): string {
  if (stage <= 0) return t('topicCardStageStart');
  if (stage >= TOPIC_CARD_COMPLETED_STAGE) return t('topicCardStageDone');
  return t('topicCardStageFilter', { n: stage });
}

/** The single question this step asks. */
export function topicStageQuestion(t: Translate, stage: number): string {
  if (stage >= TOPIC_CARD_COMPLETED_STAGE) return t('topicCardDone');
  return t(TOPIC_STAGE_QUESTION_KEYS[Math.max(stage, 0)]);
}

export function topicStageWhy(t: Translate, stage: number): string | null {
  if (stage >= TOPIC_CARD_COMPLETED_STAGE) return null;
  return t(TOPIC_STAGE_WHY_KEYS[Math.max(stage, 0)]);
}
