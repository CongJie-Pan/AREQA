'use client';

/**
 * Topic Finder (選題) topic card panel.
 *
 * One step at a time: the panel shows the current step's single question (with
 * an optional "why"), then the AI's draft from the conversation with the action
 * right under it. What is already confirmed, set-aside topics, objections, and
 * history fold away below. Fields open only when their step is reached, so a
 * learner at the first step never sees measurement jargon.
 */

import React, { useState } from 'react';
import { App } from 'antd';
import { Download, GitBranch, Telescope, X } from 'lucide-react';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import type { UseTopicCardResult } from '@/hooks/useTopicCard';
import { TOPIC_CARD_COMPLETED_STAGE, type TopicCardContent } from '@/services/topicCard';
import { downloadTopicCardMarkdown } from '@/utils/topicCardMarkdown';
import {
  MOTHER_QUESTION_STAGE, OPERATIONALIZATION_STAGE, TOPIC_STEP_COUNT,
  topicCardStageLabel, topicStageQuestion, topicStageWhy,
} from '@/utils/topicCardStages';

export { topicCardStageLabel } from '@/utils/topicCardStages';

export interface TopicCardPanelProps {
  topicCard: UseTopicCardResult;
  onClose?: () => void;
  /** Diverge: open a branch to explore one candidate; the main card is unaffected. */
  onExploreCandidate?: (candidate: string) => void;
}

type FieldKey = 'pain_point' | 'mother_question' | 'candidates' | 'operationalization';

/** Fields shown at this stage, in reading order. */
function visibleFields(stage: number): FieldKey[] {
  return [
    'pain_point',
    ...(stage >= MOTHER_QUESTION_STAGE ? ['mother_question' as const] : []),
    'candidates',
    ...(stage >= OPERATIONALIZATION_STAGE ? ['operationalization' as const] : []),
  ];
}

function hasValue(card: TopicCardContent, field: FieldKey): boolean {
  const value = card[field];
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

export function TopicCardPanel({ topicCard, onClose, onExploreCandidate }: TopicCardPanelProps) {
  const { t } = useUserPreferences();
  const { message } = App.useApp();
  const [notice, setNotice] = useState<string | null>(null);
  const [showReviseHint, setShowReviseHint] = useState(false);
  const { state, failure, isConfirming, confirm } = topicCard;
  const stage = state?.stage ?? 0;
  const isDone = stage >= TOPIC_CARD_COMPLETED_STAGE;
  const why = topicStageWhy(t, stage);

  const handleConfirm = async () => {
    const outcome = await confirm();
    if (outcome === 'advanced') {
      setNotice(null);
      setShowReviseHint(false);
      message.success(t('topicCardAdvanced'));
    } else {
      setNotice(t(outcome === 'stale' ? 'topicCardStale' : 'topicCardConfirmFailed'));
    }
  };

  const fieldLabel: Record<FieldKey, string> = {
    pain_point: t('topicCardPainPoint'),
    mother_question: t('topicCardMotherQuestion'),
    candidates: t('topicCardCandidates'),
    operationalization: t('topicCardOperationalization'),
  };

  const renderField = (card: TopicCardContent, field: FieldKey, withExplore: boolean) => {
    if (field === 'candidates') {
      return (
        <ul className="areqa-topic-card-list areqa-topic-card-candidates">
          {card.candidates.map((item) => (
            <li key={item}>
              <span>{item}</span>
              {withExplore && onExploreCandidate && (
                <button
                  type="button"
                  className="areqa-topic-card-explore"
                  onClick={() => onExploreCandidate(item)}
                  aria-label={`${t('topicCardExplore')}：${item}`}
                >
                  <GitBranch size={12} aria-hidden="true" />
                  {t('topicCardExplore')}
                </button>
              )}
            </li>
          ))}
        </ul>
      );
    }
    if (field === 'operationalization') {
      return (
        <ul className="areqa-topic-card-list areqa-topic-card-measures">
          {card.operationalization.map((item) => (
            <li key={item.term}>
              <strong>{item.term}</strong>
              {item.measure
                ? <span>{item.measure}</span>
                : <span className="areqa-topic-card-missing">❗ {t('topicCardMeasureMissing')}</span>}
            </li>
          ))}
        </ul>
      );
    }
    return <p>{card[field]}</p>;
  };

  const fieldsBlock = (card: TopicCardContent, fields: FieldKey[], withExplore: boolean) => (
    <dl className="areqa-topic-card-fields">
      {fields.filter((field) => hasValue(card, field)).map((field) => (
        <div key={field} className="areqa-topic-card-field">
          <dt>{fieldLabel[field]}</dt>
          <dd>{renderField(card, field, withExplore)}</dd>
        </div>
      ))}
    </dl>
  );

  const confirmedFields = state ? visibleFields(stage).filter((field) => hasValue(state.card, field)) : [];
  const draftFields = state?.pending
    ? visibleFields(stage).filter((field) => hasValue(state.pending!.card, field)
      && JSON.stringify(state.pending!.card[field]) !== JSON.stringify(state.card[field]))
    : [];

  return (
    <div className="areqa-topic-card" aria-label={t('topicCardTitle')} role="region">
      <header className="areqa-topic-card-header">
        <Telescope size={16} aria-hidden="true" />
        <h2>{t('topicCardTitle')}</h2>
        {state && <span className="areqa-topic-card-version">{t('topicCardVersion', { n: state.version })}</span>}
        {state && (
          <button
            type="button"
            className="areqa-topic-card-icon-button"
            onClick={() => downloadTopicCardMarkdown(state, t)}
            aria-label={t('topicCardExport')}
            title={t('topicCardExport')}
          >
            <Download size={16} />
          </button>
        )}
        {onClose && (
          <button type="button" className="areqa-topic-card-icon-button" onClick={onClose} aria-label={t('topicCardClose')}>
            <X size={16} />
          </button>
        )}
      </header>

      {failure && !state && (
        <p className="areqa-topic-card-muted" role="status">
          {t(failure === 'not_synced' ? 'topicCardNotSynced' : 'topicCardUnavailable')}
        </p>
      )}

      {state && (
        <>
          <section className="areqa-topic-card-step" aria-label={t('topicCardProgress')}>
            <div className="areqa-topic-card-step-head">
              <span className="areqa-topic-card-step-label">{topicCardStageLabel(t, stage)}</span>
              <ol className="areqa-topic-card-dots" aria-hidden="true">
                {Array.from({ length: TOPIC_STEP_COUNT }, (_, index) => {
                  const step = index + 1;
                  const status = step < stage ? 'done' : step === stage ? 'current' : 'todo';
                  return <li key={step} data-status={status} />;
                })}
              </ol>
            </div>
            {!isDone && <p className="areqa-topic-card-step-caption">{t('topicCardCurrentQuestion')}</p>}
            <p className="areqa-topic-card-question">{topicStageQuestion(t, stage)}</p>
            {why && (
              <details className="areqa-topic-card-why">
                <summary>{t('topicCardWhy')}</summary>
                <p>{why}</p>
              </details>
            )}
          </section>

          {!isDone && (
            <section className="areqa-topic-card-action">
              {state.pending && (draftFields.length > 0 || state.pending.notes.length > 0) ? (
                <div className="areqa-topic-card-draft" role="note">
                  <p className="areqa-topic-card-draft-title">{t('topicCardDraftTitle')}</p>
                  {draftFields.length > 0
                    ? fieldsBlock(state.pending.card, draftFields, false)
                    : <ul className="areqa-topic-card-list">{state.pending.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
                </div>
              ) : null}
              <div className="areqa-topic-card-buttons">
                <button
                  type="button"
                  className="areqa-topic-card-confirm"
                  onClick={() => { void handleConfirm(); }}
                  disabled={isConfirming}
                >
                  {t(state.pending ? 'topicCardAccept' : 'topicCardAdvance')}
                </button>
                {state.pending && (
                  <button type="button" className="areqa-topic-card-secondary" onClick={() => setShowReviseHint(true)}>
                    {t('topicCardRevise')}
                  </button>
                )}
              </div>
              <p className="areqa-topic-card-hint">{showReviseHint ? t('topicCardReviseHint') : t('topicCardConfirmHint')}</p>
              {notice && <p className="areqa-topic-card-notice" role="alert">{notice}</p>}
            </section>
          )}

          <details className="areqa-topic-card-fold" open>
            <summary>{t('topicCardCurrentTopic')}</summary>
            {confirmedFields.length > 0
              ? fieldsBlock(state.card, confirmedFields, true)
              : <p className="areqa-topic-card-muted">{t('topicCardEmpty')}</p>}
          </details>

          {state.card.discarded.length > 0 && (
            <details className="areqa-topic-card-fold">
              <summary>{t('topicCardDiscarded')} ({state.card.discarded.length})</summary>
              <ul className="areqa-topic-card-list areqa-topic-card-discarded">
                {state.card.discarded.map((item) => (
                  <li key={item.topic}>
                    <span>{item.topic}</span>
                    <small>
                      {[
                        item.filter > 0 ? t('topicCardDiscardedBy', { n: item.filter }) : '',
                        item.reason,
                        item.can_return ? t('topicCardCanReturn') : '',
                      ].filter(Boolean).join(' · ')}
                    </small>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {state.card.objections.length > 0 && (
            <details className="areqa-topic-card-fold">
              <summary>{t('topicCardObjections')} ({state.card.objections.length})</summary>
              <ul className="areqa-topic-card-list">{state.card.objections.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
          )}

          {state.history.length > 0 && (
            <details className="areqa-topic-card-fold">
              <summary>{t('topicCardHistory')} ({state.history.length})</summary>
              <ul className="areqa-topic-card-list">
                {state.history.map((entry) => (
                  <li key={entry.version}>
                    v{entry.version} · {topicCardStageLabel(t, entry.stage)}{entry.note ? `：${entry.note}` : ''}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {isDone && notice && <p className="areqa-topic-card-notice" role="alert">{notice}</p>}
        </>
      )}
    </div>
  );
}

export default TopicCardPanel;
