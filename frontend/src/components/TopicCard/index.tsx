'use client';

/**
 * Topic Finder (選題) topic card panel.
 *
 * Shows the learner's converging topic: pain point, core question, candidates,
 * measures, discarded candidates, and their own objections. AI proposals are
 * labelled as suggestions; only the learner's "confirm" button adopts them and
 * advances a stage.
 */

import React, { useState } from 'react';
import { App } from 'antd';
import { Check, Circle, CircleDot, Telescope, X } from 'lucide-react';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import type { TranslationKey } from '@/contexts/UserPreferencesContext';
import type { UseTopicCardResult } from '@/hooks/useTopicCard';
import { TOPIC_CARD_COMPLETED_STAGE, visibleCard } from '@/services/topicCard';

type Translate = (key: TranslationKey, params?: Record<string, string | number>) => string;

const FILTER_KEYS: TranslationKey[] = ['topicCardFilter1', 'topicCardFilter2', 'topicCardFilter3', 'topicCardFilter4', 'topicCardFilter5'];

/** "痛點", "篩子 3/5：核心", or "完成" for the learner-confirmed stage. */
export function topicCardStageLabel(t: Translate, stage: number): string {
  if (stage <= 0) return t('topicCardStagePainPoint');
  if (stage >= TOPIC_CARD_COMPLETED_STAGE) return t('topicCardStageDone');
  return t('topicCardStageFilter', { n: stage, name: t(FILTER_KEYS[stage - 1]) });
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="areqa-topic-card-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

export interface TopicCardPanelProps {
  topicCard: UseTopicCardResult;
  onClose?: () => void;
}

export function TopicCardPanel({ topicCard, onClose }: TopicCardPanelProps) {
  const { t } = useUserPreferences();
  const { message } = App.useApp();
  const [notice, setNotice] = useState<string | null>(null);
  const { state, failure, isConfirming, confirm } = topicCard;
  const card = state ? visibleCard(state) : null;
  const isDone = (state?.stage ?? 0) >= TOPIC_CARD_COMPLETED_STAGE;
  const steps = [t('topicCardStagePainPoint'), ...FILTER_KEYS.map((key) => t(key))];

  const handleConfirm = async () => {
    const outcome = await confirm();
    if (outcome === 'advanced') {
      setNotice(null);
      message.success(t('topicCardAdvanced'));
    } else {
      setNotice(t(outcome === 'stale' ? 'topicCardStale' : 'topicCardConfirmFailed'));
    }
  };

  return (
    <div className="areqa-topic-card" aria-label={t('topicCardTitle')} role="region">
      <header className="areqa-topic-card-header">
        <Telescope size={16} aria-hidden="true" />
        <h2>{t('topicCardTitle')}</h2>
        {state && <span className="areqa-topic-card-version">{t('topicCardVersion', { n: state.version })}</span>}
        {onClose && (
          <button type="button" className="areqa-topic-card-close" onClick={onClose} aria-label={t('topicCardClose')}>
            <X size={16} />
          </button>
        )}
      </header>

      {failure && !state && (
        <p className="areqa-topic-card-muted" role="status">
          {t(failure === 'not_synced' ? 'topicCardNotSynced' : 'topicCardUnavailable')}
        </p>
      )}

      {state && card && (
        <>
          <Section title={t('topicCardProgress')}>
            <ol className="areqa-topic-card-steps">
              {steps.map((label, index) => {
                const status = index < state.stage ? 'done' : index === state.stage ? 'current' : 'todo';
                const Icon = status === 'done' ? Check : status === 'current' ? CircleDot : Circle;
                return (
                  <li key={label} data-status={status} aria-current={status === 'current' ? 'step' : undefined}>
                    <Icon size={13} aria-hidden="true" />
                    <span>{index === 0 ? label : `${index}. ${label}`}</span>
                  </li>
                );
              })}
            </ol>
          </Section>

          {state.pending && (
            <p className="areqa-topic-card-pending" role="note">
              {t('topicCardPending')}
              {state.pending.notes.length > 0 && <span>{state.pending.notes.join('；')}</span>}
            </p>
          )}

          {!card.pain_point && !card.mother_question && card.candidates.length === 0 && (
            <p className="areqa-topic-card-muted">{t('topicCardEmpty')}</p>
          )}
          {card.pain_point && <Section title={t('topicCardPainPoint')}><p>{card.pain_point}</p></Section>}
          {card.mother_question && <Section title={t('topicCardMotherQuestion')}><p>{card.mother_question}</p></Section>}
          {card.candidates.length > 0 && (
            <Section title={t('topicCardCandidates')}>
              <ul>{card.candidates.map((item) => <li key={item}>{item}</li>)}</ul>
            </Section>
          )}
          {card.operationalization.length > 0 && (
            <Section title={t('topicCardOperationalization')}>
              <ul className="areqa-topic-card-measures">
                {card.operationalization.map((item) => (
                  <li key={item.term}>
                    <strong>{item.term}</strong>
                    {item.measure
                      ? <span>{item.measure}</span>
                      : <span className="areqa-topic-card-missing">❗ {t('topicCardMeasureMissing')}</span>}
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {card.discarded.length > 0 && (
            <Section title={t('topicCardDiscarded')}>
              <ul className="areqa-topic-card-discarded">
                {card.discarded.map((item) => (
                  <li key={item.topic}>
                    <span>✂ {item.topic}</span>
                    <small>
                      {item.filter > 0 ? `${t('topicCardDiscardedBy', { n: item.filter })} · ` : ''}{item.reason}
                      {item.can_return ? ` · ${t('topicCardCanReturn')}` : ''}
                    </small>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {card.objections.length > 0 && (
            <Section title={t('topicCardObjections')}>
              <ul>{card.objections.map((item) => <li key={item}>{item}</li>)}</ul>
            </Section>
          )}

          <footer className="areqa-topic-card-footer">
            {isDone ? (
              <p className="areqa-topic-card-muted">{t('topicCardDone')}</p>
            ) : (
              <>
                <button
                  type="button"
                  className="areqa-topic-card-confirm"
                  onClick={() => { void handleConfirm(); }}
                  disabled={isConfirming}
                >
                  {t('topicCardConfirm')}
                </button>
                <p className="areqa-topic-card-hint">{t('topicCardConfirmHint')}</p>
              </>
            )}
            {notice && <p className="areqa-topic-card-notice" role="alert">{notice}</p>}
          </footer>
        </>
      )}
    </div>
  );
}

export default TopicCardPanel;
