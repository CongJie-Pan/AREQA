/**
 * Topic Finder (選題) topic card → Markdown, for the learner's own notes.
 *
 * Learner text is escaped so a pasted heading, list marker, link, or table pipe
 * stays literal instead of reshaping the document.
 */

import type { TranslationKey } from '@/contexts/UserPreferencesContext';
import { TOPIC_FEASIBILITY_KEYS, type TopicCardState, type TopicFeasibilityItem, visibleCard } from '@/services/topicCard';
import { topicCardStageLabel, topicStageTitle } from '@/utils/topicCardStages';

type Translate = (key: TranslationKey, params?: Record<string, string | number>) => string;

/** Escape Markdown syntax and fold line breaks so each value stays on its own line. */
export function escapeMarkdown(value: string): string {
  return value
    .replace(/\r?\n+/g, ' ')
    .replace(/([\\`*_{}[\]()#+\-.!|<>~])/g, '\\$1')
    .trim();
}

const FEASIBILITY_LABELS = {
  time: 'topicFeasTime', data: 'topicFeasData', advisor: 'topicFeasAdvisor', prior_work: 'topicFeasPriorWork',
  ethics: 'topicFeasEthics',
} as const;
const FEASIBILITY_STATUS = {
  ok: ['✅', 'topicFeasOk'], unsure: ['⚠️', 'topicFeasUnsure'], blocked: ['❌', 'topicFeasBlocked'],
} as const;

function feasibilityLines(items: TopicFeasibilityItem[], t: Translate): string[] {
  if (!items.length) return ['—'];
  const byKey = new Map(items.map((item) => [item.key, item]));
  return TOPIC_FEASIBILITY_KEYS.map((key) => {
    const item = byKey.get(key);
    const [icon, label] = item ? FEASIBILITY_STATUS[item.status] : ['⚠️', 'topicFeasMissing' as const];
    return `- ${t(FEASIBILITY_LABELS[key])}: ${icon} ${t(label)}${item?.note ? ` · ${escapeMarkdown(item.note)}` : ''}`;
  });
}

/** Markdown for the confirmed card plus any pending AI draft, labelled as such. */
export function topicCardToMarkdown(state: TopicCardState, t: Translate): string {
  const card = state.card;
  const lines = [
    `# ${t('topicCardTitle')}`,
    '',
    `- ${t('topicCardProgress')}: ${topicCardStageLabel(t, state.stage)}`,
    `- ${escapeMarkdown(topicStageTitle(t, state.stage))}`,
    `- ${t('topicCardVersion', { n: state.version })}`,
    '',
    `## ${t('topicCardPainPoint')}`,
    card.pain_point ? escapeMarkdown(card.pain_point) : '—',
    '',
    `## ${t('topicCardMotherQuestion')}`,
    card.mother_question ? escapeMarkdown(card.mother_question) : '—',
    '',
    `## ${t('topicCardCandidates')}`,
    ...(card.candidates.length
      ? card.candidates.map((item) => `- ${escapeMarkdown(item)}${card.ai_candidates?.includes(item) ? ` (${t('topicCardAiProposed')})` : ''}`)
      : ['—']),
    '',
    `## ${t('topicCardOperationalization')}`,
    ...(card.operationalization.length
      ? card.operationalization.map((item) => `- ${escapeMarkdown(item.term)}: ${item.measure ? escapeMarkdown(item.measure) : `⚠️ ${t('topicCardMeasureMissing')}`}`)
      : ['—']),
    '',
    `## ${t('topicCardFeasibility')}`,
    ...feasibilityLines(card.feasibility ?? [], t),
    '',
    `## ${t('topicCardDiscarded')}`,
    ...(card.discarded.length
      ? card.discarded.map((item) => [
        `- ${escapeMarkdown(item.topic)}`,
        item.filter > 0 ? ` (${t('topicCardDiscardedBy', { n: item.filter })})` : '',
        item.reason ? `: ${escapeMarkdown(item.reason)}` : '',
        item.can_return ? ` · ${t('topicCardCanReturn')}` : '',
      ].join(''))
      : ['—']),
    '',
    `## ${t('topicCardObjections')}`,
    ...(card.objections.length ? card.objections.map((item) => `- ${escapeMarkdown(item)}`) : ['—']),
    '',
    `## ${t('topicCardHistory')}`,
    ...(state.history.length
      ? state.history.map((entry) => `- v${entry.version} · ${topicCardStageLabel(t, entry.stage)}${entry.note ? `: ${escapeMarkdown(entry.note)}` : ''}`)
      : ['—']),
  ];
  if (state.pending) {
    const draft = visibleCard(state);
    lines.push('', `## ${t('topicCardPending')}`);
    if (state.pending.notes.length) lines.push(...state.pending.notes.map((note) => `- ${escapeMarkdown(note)}`));
    if (draft.pain_point && draft.pain_point !== card.pain_point) lines.push(`- ${t('topicCardPainPoint')}: ${escapeMarkdown(draft.pain_point)}`);
    if (draft.mother_question && draft.mother_question !== card.mother_question) {
      lines.push(`- ${t('topicCardMotherQuestion')}: ${escapeMarkdown(draft.mother_question)}`);
    }
  }
  return `${lines.join('\n')}\n`;
}

export function downloadTopicCardMarkdown(state: TopicCardState, t: Translate): void {
  const blob = new Blob([topicCardToMarkdown(state, t)], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `areqa-topic-card-v${state.version}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoke after the browser has started the download.
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
