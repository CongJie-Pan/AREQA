'use client';

/**
 * Topic Finder (選題) topic card panel.
 *
 * The conversation does the thinking; the card only keeps what the learner has
 * decided. So the panel shows, top to bottom: the stage stepper with the stage
 * label, goal and subtitle, the topic headline (mother question, else pain point), the
 * one field the current stage works on, and the AI draft as a yes/no question
 * listing only what would change. Everything else folds into one "other
 * records" line. Stage explanations, focus hints and "move on" prompts live in
 * the conversation instead of on the card.
 */

import React, { useState } from 'react';
import { App } from 'antd';
import { Download, GitBranch, Telescope, X } from 'lucide-react';
import { type TranslationKey, useUserPreferences } from '@/contexts/UserPreferencesContext';
import type { UseTopicCardResult } from '@/hooks/useTopicCard';
import {
  TOPIC_CARD_COMPLETED_STAGE, TOPIC_FEASIBILITY_KEYS, type TopicCardContent, type TopicFeasibilityItem,
  type TopicFeasibilityKey,
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

type ListField = 'candidates' | 'operationalization' | 'feasibility';
type FieldKey = 'pain_point' | 'mother_question' | ListField;

export const FEASIBILITY_LABEL_KEYS: Record<TopicFeasibilityKey, TranslationKey> = {
  time: 'topicFeasTime', data: 'topicFeasData', advisor: 'topicFeasAdvisor', prior_work: 'topicFeasPriorWork',
  ethics: 'topicFeasEthics',
};

export const FEASIBILITY_STATUS: Record<TopicFeasibilityItem['status'], { icon: string; key: TranslationKey }> = {
  ok: { icon: '✅', key: 'topicFeasOk' },
  unsure: { icon: '⚠️', key: 'topicFeasUnsure' },
  blocked: { icon: '❌', key: 'topicFeasBlocked' },
};

/** The field each stage works on; it stays open on the card while the rest folds away. */
const STAGE_FIELD: Record<number, ListField> = {
  1: 'candidates', 2: 'candidates', 3: 'candidates', 4: 'operationalization', 5: 'feasibility',
};

/** A field may be drafted from the stage that asks about it, or once it already has content. */
const FIELD_OPENS: Record<FieldKey, number> = {
  pain_point: 1, candidates: 1, mother_question: MOTHER_QUESTION_STAGE,
  operationalization: OPERATIONALIZATION_STAGE, feasibility: FEASIBILITY_STAGE,
};

function hasValue(card: TopicCardContent, field: FieldKey): boolean {
  const value = card[field];
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

/** One line of a draft: what would be added or changed (or a candidate that would leave the list). */
interface DraftLine {
  key: string;
  field: FieldKey | 'discarded';
  text: string;
  removed?: boolean;
  aiProposed?: boolean;
  missingMeasure?: boolean;
}

/** Only what the draft changes against the adopted card, so the learner reads the difference, not the list. */
function draftLines(base: TopicCardContent, draft: TopicCardContent, stage: number,
  feasibilityText: (item: TopicFeasibilityItem) => string): DraftLine[] {
  const opens = (field: FieldKey) => stage >= FIELD_OPENS[field] || hasValue(base, field);
  const lines: DraftLine[] = [];
  for (const field of ['pain_point', 'mother_question'] as const) {
    if (opens(field) && draft[field] && draft[field] !== base[field]) {
      lines.push({ key: field, field, text: draft[field] });
    }
  }
  if (opens('candidates')) {
    for (const item of draft.candidates.filter((candidate) => !base.candidates.includes(candidate))) {
      lines.push({ key: `add:${item}`, field: 'candidates', text: item, aiProposed: draft.ai_candidates?.includes(item) });
    }
    const dropped = new Set(draft.discarded.map((item) => item.topic));
    for (const item of base.candidates.filter((candidate) => !draft.candidates.includes(candidate) && !dropped.has(candidate))) {
      lines.push({ key: `remove:${item}`, field: 'candidates', text: item, removed: true });
    }
  }
  if (opens('operationalization')) {
    const before = new Map(base.operationalization.map((item) => [item.term, item.measure]));
    for (const item of draft.operationalization.filter((term) => before.get(term.term) !== term.measure)) {
      lines.push({
        key: `term:${item.term}`, field: 'operationalization',
        text: item.measure ? `${item.term}：${item.measure}` : item.term, missingMeasure: !item.measure,
      });
    }
  }
  if (opens('feasibility')) {
    const before = new Map((base.feasibility ?? []).map((item) => [item.key, JSON.stringify(item)]));
    for (const item of (draft.feasibility ?? []).filter((check) => before.get(check.key) !== JSON.stringify(check))) {
      lines.push({ key: `feas:${item.key}`, field: 'feasibility', text: feasibilityText(item) });
    }
  }
  const known = new Set(base.discarded.map((item) => item.topic));
  for (const item of draft.discarded.filter((topic) => !known.has(topic.topic))) {
    lines.push({ key: `drop:${item.topic}`, field: 'discarded', text: item.reason ? `${item.topic}（${item.reason}）` : item.topic });
  }
  return lines;
}

export function TopicCardPanel({ topicCard, onClose, onExploreCandidate }: TopicCardPanelProps) {
  const { t } = useUserPreferences();
  const { message } = App.useApp();
  const [notice, setNotice] = useState<string | null>(null);
  const { state, failure, isSaving, adopt, reject, goToStage } = topicCard;
  const stage = normalizeTopicStage(state?.stage ?? 1);
  const isDone = stage >= TOPIC_CARD_COMPLETED_STAGE;

  const handleAdopt = async () => {
    const outcome = await adopt();
    if (outcome === 'adopted') {
      setNotice(null);
      message.success(t('topicCardAdopted'));
    } else {
      setNotice(t(outcome === 'stale' ? 'topicCardStale' : 'topicCardConfirmFailed'));
    }
  };

  const handleReject = async () => {
    const outcome = await reject();
    if (outcome === 'rejected') {
      setNotice(null);
      message.info(t('topicCardRejected'));
    } else {
      setNotice(t(outcome === 'stale' ? 'topicCardStale' : 'topicCardConfirmFailed'));
    }
  };

  const handleStage = async (target: number) => {
    if (target === stage) return;
    const moved = await goToStage(target);
    setNotice(moved ? null : t('topicCardStageFailed'));
  };

  const copyKeyword = (keyword: string) => {
    void navigator.clipboard?.writeText(keyword).then(
      () => message.success(t('topicCardKeywordCopied')),
      () => undefined,
    );
  };

  const fieldLabel: Record<FieldKey | 'discarded', string> = {
    pain_point: t('topicCardPainPoint'),
    mother_question: t('topicCardMotherQuestion'),
    candidates: t('topicCardCandidates'),
    operationalization: t('topicCardOperationalization'),
    feasibility: t('topicCardFeasibility'),
    discarded: t('topicCardDiscarded'),
  };

  const feasibilityText = (item: TopicFeasibilityItem) => {
    const status = FEASIBILITY_STATUS[item.status];
    return `${t(FEASIBILITY_LABEL_KEYS[item.key])}：${status.icon} ${t(status.key)}${item.note ? `（${item.note}）` : ''}`;
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

  const renderList = (card: TopicCardContent, field: ListField, isStageField: boolean) => {
    if (field === 'candidates') {
      return (
        <ul className="areqa-topic-card-list areqa-topic-card-candidates">
          {card.candidates.map((item) => (
            <li key={item}>
              <span>{item}</span>
              {card.ai_candidates?.includes(item) && (
                <span className="areqa-topic-card-ai-tag" title={t('topicCardAiProposedHint')}>{t('topicCardAiProposed')}</span>
              )}
              {onExploreCandidate && (
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
    // On its own stage the checklist lists every check, so the unanswered ones show.
    return renderFeasibility(card.feasibility ?? [], isStageField);
  };

  const stageField = isDone ? null : STAGE_FIELD[stage];
  const showStageField = Boolean(state && stageField && (stageField === 'feasibility' || hasValue(state.card, stageField)));
  const otherFields = state
    ? (['candidates', 'operationalization', 'feasibility'] as ListField[])
      .filter((field) => (field !== stageField || !showStageField) && hasValue(state.card, field))
    : [];
  const otherSummary = state ? [
    ...otherFields.map((field) => fieldLabel[field]),
    state.card.discarded.length ? t('topicCardCountDiscarded', { n: state.card.discarded.length }) : '',
    state.card.objections.length ? t('topicCardCountObjections', { n: state.card.objections.length }) : '',
    state.history.length ? t('topicCardCountVersions', { n: state.history.length }) : '',
  ].filter(Boolean) : [];

  const lines = state?.pending ? draftLines(state.card, state.pending.card, stage, feasibilityText) : [];
  // A draft that only adds candidates gets the narrower question.
  const draftQuestion = lines.length > 0 && lines.every((line) => line.field === 'candidates' && !line.removed)
    ? 'topicCardDraftCandidatesQuestion' : 'topicCardDraftQuestion';
  const keywords = stage <= 2 ? state?.suggestions?.keywords ?? [] : [];
  const headline = state?.card.mother_question || state?.card.pain_point;

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
          </section>

          <section className="areqa-topic-card-topic">
            {headline ? (
              <>
                <p className="areqa-topic-card-label">{t(state.card.mother_question ? 'topicCardMotherQuestion' : 'topicCardPainPoint')}</p>
                <p className="areqa-topic-card-headline">{headline}</p>
                {state.card.mother_question && state.card.pain_point && (
                  <p className="areqa-topic-card-subline" title={state.card.pain_point}>{state.card.pain_point}</p>
                )}
              </>
            ) : (
              <p className="areqa-topic-card-muted">{t('topicCardEmpty')}</p>
            )}
            {keywords.length > 0 && (
              <div className="areqa-topic-card-chips" aria-label={t('topicCardKeywords')}>
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
            )}
          </section>

          {showStageField && stageField && (
            <section className="areqa-topic-card-stage-field" aria-label={fieldLabel[stageField]}>
              <p className="areqa-topic-card-label">{fieldLabel[stageField]}</p>
              {renderList(state.card, stageField, true)}
            </section>
          )}

          {state.pending && (
            <div className="areqa-topic-card-draft" role="group" aria-label={t(draftQuestion)}>
              <p className="areqa-topic-card-draft-question">{t(draftQuestion)}</p>
              {lines.length > 0 ? (
                <ul className="areqa-topic-card-draft-lines">
                  {lines.map((line) => (
                    <li key={line.key} data-change={line.removed ? 'remove' : 'add'}>
                      <small>{line.removed ? t('topicCardDraftRemoved', { field: fieldLabel[line.field] }) : fieldLabel[line.field]}</small>
                      <span>
                        {line.text}
                        {line.aiProposed && (
                          <span className="areqa-topic-card-ai-tag" title={t('topicCardAiProposedHint')}>{t('topicCardAiProposed')}</span>
                        )}
                        {line.missingMeasure && <span className="areqa-topic-card-missing"> ⚠️ {t('topicCardMeasureMissing')}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : state.pending.notes.length > 0 && (
                <ul className="areqa-topic-card-list">{state.pending.notes.map((note) => <li key={note}>{note}</li>)}</ul>
              )}
              <div className="areqa-topic-card-buttons">
                <button type="button" className="areqa-topic-card-confirm" onClick={() => { void handleAdopt(); }} disabled={isSaving}>
                  {t('topicCardDraftYes')}
                </button>
                <button type="button" className="areqa-topic-card-secondary" onClick={() => { void handleReject(); }} disabled={isSaving}>
                  {t('topicCardDraftNo')}
                </button>
              </div>
            </div>
          )}

          {notice && <p className="areqa-topic-card-notice" role="alert">{notice}</p>}

          {otherSummary.length > 0 && (
            <details className="areqa-topic-card-fold areqa-topic-card-more">
              <summary>
                <span className="areqa-topic-card-more-title">{t('topicCardMoreRecords')}</span>
                <small>{otherSummary.join(' · ')}</small>
              </summary>
              {otherFields.map((field) => (
                <div key={field} className="areqa-topic-card-group">
                  <p className="areqa-topic-card-group-label">{fieldLabel[field]}</p>
                  {renderList(state.card, field, false)}
                </div>
              ))}
              {state.card.discarded.length > 0 && (
                <div className="areqa-topic-card-group">
                  <p className="areqa-topic-card-group-label">
                    {t('topicCardDiscarded')}<span>{state.card.discarded.length}</span>
                  </p>
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
                </div>
              )}
              {state.card.objections.length > 0 && (
                <div className="areqa-topic-card-group">
                  <p className="areqa-topic-card-group-label">
                    {t('topicCardObjections')}<span>{state.card.objections.length}</span>
                  </p>
                  <ul className="areqa-topic-card-list">{state.card.objections.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
              )}
              {state.history.length > 0 && (
                <div className="areqa-topic-card-group">
                  <p className="areqa-topic-card-group-label">
                    {t('topicCardHistory')}<span>{state.history.length}</span>
                  </p>
                  {/* Newest first: the latest change is what the learner usually looks for. */}
                  <ol className="areqa-topic-card-history">
                    {[...state.history].reverse().map((entry) => (
                      <li key={entry.version}>
                        <span className="areqa-topic-card-history-version">v{entry.version}</span>
                        <span className="areqa-topic-card-history-note">
                          {entry.note || '—'}
                          <small>{topicCardStageLabel(t, entry.stage)}</small>
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </details>
          )}
        </>
      )}
    </div>
  );
}

export default TopicCardPanel;
