'use client';

/**
 * One-tap "move on" for Topic Finder, shown above the composer once the adopted
 * card covers the current stage. Tapping sends an ordinary learner message
 * ("好，我們進到第 4 階段：…"); the backend applies the explicit request and
 * the coach opens the new stage in its reply, so the move stays the learner's.
 */

import React, { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import type { UseTopicCardResult } from '@/hooks/useTopicCard';
import { TOPIC_CARD_COMPLETED_STAGE } from '@/services/topicCard';
import { topicStageTitle } from '@/utils/topicCardStages';

export interface TopicStageNudgeProps {
  topicCard: UseTopicCardResult;
  /** Hidden while an answer streams; disabled while sending is not possible. */
  isStreaming: boolean;
  disabled?: boolean;
  onSend: (message: string) => Promise<unknown> | void;
}

export function TopicStageNudge({ topicCard, isStreaming, disabled, onSend }: TopicStageNudgeProps) {
  const { t } = useUserPreferences();
  // The stage the learner just moved on from; hides the nudge until the card reloads.
  const [movedFrom, setMovedFrom] = useState<number | null>(null);
  const state = topicCard.state;
  const nextStage = state?.next_stage;
  if (!state || !nextStage || isStreaming || movedFrom === state.stage) return null;

  const finishing = nextStage >= TOPIC_CARD_COMPLETED_STAGE;
  const title = finishing ? '' : topicStageTitle(t, nextStage);
  const label = finishing ? t('topicStageFinishButton') : t('topicStageMoveButton', { n: nextStage, title });
  const message = finishing ? t('topicStageFinishMessage') : t('topicStageMoveMessage', { n: nextStage, title });

  return (
    <div className="areqa-topic-stage-nudge">
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          setMovedFrom(state.stage);
          void Promise.resolve(onSend(message)).catch(() => undefined);
        }}
      >
        <span>{label}</span>
        <ArrowRight size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

export default TopicStageNudge;
