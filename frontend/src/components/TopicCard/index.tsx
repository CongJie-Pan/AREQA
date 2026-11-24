'use client';

/**
 * Topic Finder (選題) topic card panel.
 *
 * The learner picks one of five stages (in any order) from the stepper; the
 * panel shows that stage's one-line goal and subtitle, AI search hints for the
 * early stages, then the AI's draft with the actions right under it. What is
 * already adopted, set-aside topics, objections, and history fold away below.
 * A field opens at the stage that asks about it, or once it has content, so a
 * learner at stage 1 never sees measurement jargon but jumping back keeps work.
 * Under the stage goal, a quiet line says what the coach looks at next: a
 * check-back after a revision, or one card gap the learner can set aside.
 */

import React, { useState } from 'react';
import { App } from 'antd';
import { Download, GitBranch, Search, Telescope, Undo2, X } from 'lucide-react';
import { type TranslationKey, useUserPreferences } from '@/contexts/UserPreferencesContext';
import type { UseTopicCardResult } from '@/hooks/useTopicCard';
import {
  TOPIC_CARD_COMPLETED_STAGE, TOPIC_FEASIBILITY_KEYS, type TopicCardContent, type TopicFeasibilityItem,
  type TopicFeasibilityKey, type TopicFocusGap, type TopicFocusKind,
} from '@/services/topicCard';
import { downloadTopicCardMarkdown } from '@/utils/topicCardMarkdown';
import {
  FEASIBILITY_STAGE, MOTHER_QUESTION_STAGE, OPERATIONALIZATION_STAGE, TOPIC_STEP_COUNT,
  normalizeTopicStage, topicCardStageLabel, topicStageSubtitle, topicStageTitle,
} from '@/utils/topicCardStages';

export { topicCardStageLabel } from '@/utils/topicCardStages';

export interface TopicCardPanelProps {
  topicCard: UseTopicCardResult;
  onClose?: () => void;
  /** Diverge: open a branch to explore one candidate; the main card is unaffected. */
  onExploreCandidate?: (candidate: string) => void;
}

type FieldKey = 'pain_point' | 'mother_question' | 'candidates' | 'operationalization' | 'feasibility';

export const FEASIBILITY_LABEL_KEYS: Record<TopicFeasibilityKey, TranslationKey> = {
  time: 'topicFeasTime', data: 'topicFeasData', advisor: 'topicFeasAdvisor', prior_work: 'topicFeasPriorWork',
  ethics: 'topicFeasEthics',
};

export const FEASIBILITY_STATUS: Record<TopicFeasibilityItem['status'], { icon: string; key: TranslationKey }> = {
  ok: { icon: '✅', key: 'topicFeasOk' },
  unsure: { icon: '⚠️', key: 'topicFeasUnsure' },
  blocked: { icon: '❌', key: 'topicFeasBlocked' },
};

const FOCUS_LABEL_KEYS: Record<TopicFocusKind, TranslationKey> = {
  pain_point: 'topicFocusPainPoint',
  candidates: 'topicFocusCandidates',
  own_candidate: 'topicFocusOwnCandidate',
  mother_question: 'topicFocusMotherQuestion',
  operationalization: 'topicFocusOperationalization',
  measure: 'topicFocusMeasure',
  feasibility_missing: 'topicFocusFeasibilityMissing',
  feasibility_unsure: 'topicFocusFeasibilityUnsure',
};

export function topicFocusLabel(t: (key: TranslationKey, vars?: Record<string, string | number>) => string,
  focus: TopicFocusGap): string {
  const feasibilityKey = FEASIBILITY_LABEL_KEYS[focus.term as TopicFeasibilityKey];
  return t(FOCUS_LABEL_KEYS[focus.kind], { term: feasibilityKey ? t(feasibilityKey) : focus.term });
}

function hasValue(card: TopicCardContent, field: FieldKey): boolean {
  const value = card[field];
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

/** Fields shown in reading order: open from their stage, or once they have content. */
function visibleFields(stage: number, card: TopicCardContent): FieldKey[] {
  const opens = (field: FieldKey, from: number) => stage >= from || hasValue(card, field);
  return [
    'pain_point',
    ...(opens('mother_question', MOTHER_QUESTION_STAGE) ? ['mother_question' as const] : []),
    'candidates',
    ...(opens('operationalization', OPERATIONALIZATION_STAGE) ? ['operationalization' as const] : []),
    ...(opens('feasibility', FEASIBILITY_STAGE) ? ['feasibility' as const] : []),
  ];
}

export function TopicCardPanel({ topicCard, onClose, onExploreCandidate }: TopicCardPanelProps) {
  const { t } = useUserPreferences();
  const { message } = App.useApp();
  const [notice, setNotice] = useState<string | null>(null);
  const [showReviseHint, setShowReviseHint] = useState(false);
  const { state, failure, isSaving, adopt, goToStage, skipFocus } = topicCard;
  const stage = normalizeTopicStage(state?.stage ?? 1);
  const isDone = stage >= TOPIC_CARD_COMPLETED_STAGE;

  const handleAdopt = async () => {
    const outcome = await adopt();
    if (outcome === 'adopted') {
      setNotice(null);
      setShowReviseHint(false);
      message.success(t('topicCardAdopted'));
    } else {
      setNotice(t(outcome === 'stale' ? 'topicCardStale' : 'topicCardConfirmFailed'));
    }
  };

  const handleStage = async (target: number) => {
    if (target === stage) return;
    const moved = await goToStage(target);
    setNotice(moved ? null : t('topicCardStageFailed'));
    if (moved) setShowReviseHint(false);
  };

  const handleSkipFocus = async (gapId: string) => {
    const skipped = await skipFocus(gapId);
    setNotice(skipped ? null : t('topicCardFocusSkipFailed'));
  };

  const copyKeyword = (keyword: string) => {
    void navigator.clipboard?.writeText(keyword).then(
      () => message.success(t('topicCardKeywordCopied')),
      () => undefined,
    );
  };

  const fieldLabel: Record<FieldKey, string> = {
    pain_point: t('topicCardPainPoint'),
    mother_question: t('topicCardMotherQuestion'),
    candidates: t('topicCardCandidates'),
    operationalization: t('topicCardOperationalization'),
    feasibility: t('topicCardFeasibility'),
  };

  const renderFeasibility = (items: TopicFeasibilityItem[], showMissing: boolean) => {
    const byKey = new Map(items.map((item) => [item.key, item]));
    const keys = showMissing ? TOPIC_FEASIBILITY_KEYS : TOPIC_FEASIBILITY_KEYS.filter((key) => byKey.has(key));
    return (
      <ul className="areqa-topic-card-feasibility">
        {keys.map((key) => {
          const item = byKey.get(key);
          const status = item ? FEASIBILITY_STATUS[item.status] : { icon: '⚠️', key: 'topicFeasMissing' as const };
          return (
            <li key={key} data-status={item?.status ?? 'missing'}>
              <span className="areqa-topic-card-feasibility-name">{t(FEASIBILITY_LABEL_KEYS[key])}</span>
              <span className="areqa-topic-card-feasibility-status">{status.icon} {t(status.key)}</span>
              {item?.note && <small>{item.note}</small>}
            </li>
          );
        })}
      </ul>
    );
  };

  const renderField = (card: TopicCardContent, field: FieldKey, confirmed: boolean) => {
    if (field === 'candidates') {
      return (
        <ul className="areqa-topic-card-list areqa-topic-card-candidates">
          {card.candidates.map((item) => (
            <li key={item}>
              <span>{item}</span>
              {card.ai_candidates?.includes(item) && (
                <span className="areqa-topic-card-ai-tag" title={t('topicCardAiProposedHint')}>{t('topicCardAiProposed')}</span>
              )}
              {confirmed && onExploreCandidate && (
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
                : <span className="areqa-topic-card-missing">⚠️ {t('topicCardMeasureMissing')}</span>}
            </li>
          ))}
        </ul>
      );
    }
    if (field === 'feasibility') return renderFeasibility(card.feasibility ?? [], confirmed);
    return <p>{card[field]}</p>;
  };

  const fieldsBlock = (card: TopicCardContent, fields: FieldKey[], confirmed: boolean) => (
    <dl className="areqa-topic-card-fields">
      {fields.map((field) => (
        <div key={field} className="areqa-topic-card-field">
          <dt>{fieldLabel[field]}</dt>
          <dd>{renderField(card, field, confirmed)}</dd>
        </div>
      ))}
    </dl>
  );

  // The feasibility checklist shows from stage 5 even before any answer, so missing checks are visible.
  const confirmedFields = state
    ? visibleFields(stage, state.card).filter((field) => hasValue(state.card, field)
      || (field === 'feasibility' && stage >= FEASIBILITY_STAGE))
    : [];
  const draftFields = state?.pending
    // Draft fields open by stage or by adopted content, so an early-stage draft cannot introduce later fields.
    ? visibleFields(stage, state.card).filter((field) => hasValue(state.pending!.card, field)
      && JSON.stringify(state.pending!.card[field] ?? []) !== JSON.stringify(state.card[field] ?? []))
    : [];
  const hasDraft = Boolean(state?.pending && (draftFields.length > 0 || state.pending.notes.length > 0));

  const suggestions = state?.suggestions;
  const keywords = stage <= 2 ? suggestions?.keywords ?? [] : [];
  const gaps = stage === 1 ? suggestions?.gaps ?? [] : [];
  const related = stage === 1 ? suggestions?.related ?? [] : [];
  const showSuggestions = keywords.length + gaps.length + related.length > 0;

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
            <ol className="areqa-topic-card-stepper">
              {Array.from({ length: TOPIC_STEP_COUNT }, (_, index) => {
                const step = index + 1;
                const status = step === stage ? 'current' : step < stage ? 'done' : 'todo';
                return (
                  <li key={step}>
                    <button
                      type="button"
                      data-status={status}
                      aria-current={step === stage ? 'step' : undefined}
                      aria-label={t('topicCardGoToStage', { n: step, title: topicStageTitle(t, step) })}
                      title={topicStageTitle(t, step)}
                      disabled={isSaving}
                      onClick={() => { void handleStage(step); }}
                    >
                      {step}
                    </button>
                  </li>
                );
              })}
            </ol>
            <p className="areqa-topic-card-step-label">{topicCardStageLabel(t, stage)}</p>
            <h3 className="areqa-topic-card-question">{topicStageTitle(t, stage)}</h3>
            <p className="areqa-topic-card-subtitle">{topicStageSubtitle(t, stage)}</p>
            {/* A pending check-back takes the coach's next question, so the focus line waits for it. */}
            {state.review ? (
              <p className="areqa-topic-card-steer" role="note">
                <Undo2 size={13} aria-hidden="true" />
                <span>{t('topicCardReviewNote', { stages: state.review.stages.join(t('topicCardStageSeparator')) })}</span>
              </p>
            ) : state.focus && !isDone ? (
              <p className="areqa-topic-card-steer" role="note">
                <Search size={13} aria-hidden="true" />
                <span>{t('topicCardFocusLabel')}{topicFocusLabel(t, state.focus)}</span>
                <button
                  type="button"
                  className="areqa-topic-card-steer-skip"
                  onClick={() => { void handleSkipFocus(state.focus!.id); }}
                  disabled={isSaving}
                  title={t('topicCardFocusSkipHint')}
                >
                  {t('topicCardFocusSkip')}
                </button>
              </p>
            ) : null}
          </section>

          {showSuggestions && (
            <section className="areqa-topic-card-suggestions" aria-label={t('topicCardSuggestions')}>
              <p className="areqa-topic-card-draft-title">{t('topicCardSuggestions')}</p>
              {keywords.length > 0 && (
                <div>
                  <p className="areqa-topic-card-suggestion-label">{t('topicCardKeywords')}</p>
                  <div className="areqa-topic-card-chips">
                    {keywords.map((keyword) => (
                      <button
                        key={keyword}
                        type="button"
                        className="areqa-topic-card-chip"
                        onClick={() => copyKeyword(keyword)}
                        aria-label={t('topicCardKeywordCopy', { keyword })}
                      >
                        {keyword}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {gaps.length > 0 && (
                <div>
                  <p className="areqa-topic-card-suggestion-label">{t('topicCardGaps')}</p>
                  <ul className="areqa-topic-card-list">{gaps.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
              )}
              {related.length > 0 && (
                <div>
                  <p className="areqa-topic-card-suggestion-label">{t('topicCardRelated')}</p>
                  <ul className="areqa-topic-card-list">{related.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
              )}
            </section>
          )}

          <section className="areqa-topic-card-action">
            {hasDraft && state.pending ? (
              <div className="areqa-topic-card-draft" role="note">
                <p className="areqa-topic-card-draft-title">{t('topicCardDraftTitle')}</p>
                {draftFields.length > 0
                  ? fieldsBlock(state.pending.card, draftFields, false)
                  : <ul className="areqa-topic-card-list">{state.pending.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
              </div>
            ) : null}
            <div className="areqa-topic-card-buttons">
              {state.pending && (
                <>
                  <button
                    type="button"
                    className="areqa-topic-card-confirm"
                    onClick={() => { void handleAdopt(); }}
                    disabled={isSaving}
                  >
                    {t('topicCardAccept')}
                  </button>
                  <button type="button" className="areqa-topic-card-secondary" onClick={() => setShowReviseHint(true)}>
                    {t('topicCardRevise')}
                  </button>
                </>
              )}
              {!isDone && (
                <button
                  type="button"
                  className={state.pending ? 'areqa-topic-card-next' : 'areqa-topic-card-confirm'}
                  onClick={() => { void handleStage(stage + 1); }}
                  disabled={isSaving}
                >
                  {t('topicCardNextStage')}
                </button>
              )}
            </div>
            <p className="areqa-topic-card-hint">{showReviseHint ? t('topicCardReviseHint') : t('topicCardConfirmHint')}</p>
            {notice && <p className="areqa-topic-card-notice" role="alert">{notice}</p>}
          </section>

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
        </>
      )}
    </div>
  );
}

export default TopicCardPanel;
