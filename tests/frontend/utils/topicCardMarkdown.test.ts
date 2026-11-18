import { describe, expect, it } from 'vitest';
import { escapeMarkdown, topicCardToMarkdown } from '@/utils/topicCardMarkdown';
import type { TopicCardState } from '@/services/topicCard';

const labels: Record<string, string> = {
  topicCardTitle: 'Topic card', topicCardProgress: 'Progress', topicCardVersion: 'Version v{n}',
  topicCardStagePainPoint: 'Pain point', topicCardStageFilter: 'Filter {n}/5: {name}', topicCardStageDone: 'Done',
  topicCardFilter1: 'Time', topicCardFilter2: 'Simplest fix', topicCardFilter3: 'Core', topicCardFilter4: 'Measurable', topicCardFilter5: 'Reality',
  topicCardPainPoint: 'Pain point', topicCardMotherQuestion: 'Core question', topicCardCandidates: 'Candidates',
  topicCardOperationalization: 'Measures', topicCardMeasureMissing: 'No measure yet', topicCardDiscarded: 'Discarded',
  topicCardDiscardedBy: 'Filter {n}', topicCardCanReturn: 'May return later', topicCardObjections: 'My objections',
  topicCardHistory: 'History', topicCardPending: 'AI suggestions',
};
const t = (key: string, params?: Record<string, string | number>) => Object.entries(params ?? {})
  .reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), labels[key] ?? key);

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };

describe('topic card Markdown', () => {
  it('exports every section, the stage, and the version history', () => {
    const markdown = topicCardToMarkdown({
      stage: 4, version: 4,
      card: {
        pain_point: 'AREQA feels like Gemini', mother_question: 'How do AI replies shape reasoning',
        candidates: ['Reply strategy'], operationalization: [{ term: 'Depth', measure: '' }, { term: 'Engagement', measure: 'follow-ups' }],
        discarded: [{ topic: 'Memory', filter: 1, reason: 'solved by progress', can_return: true }],
        objections: ['Too many questions annoy me'],
      },
      pending: { card: { ...empty, pain_point: 'AREQA feels like Gemini', mother_question: 'Revised question' }, notes: ['revised'] },
      history: [{ version: 1, stage: 1, note: 'pain point', confirmed_at: 1 }],
    }, t as never);

    expect(markdown).toContain('# Topic card');
    expect(markdown).toContain('- Progress: Filter 4/5: Measurable');
    expect(markdown).toContain('- Depth: ❗ No measure yet');
    expect(markdown).toContain('- Engagement: follow\\-ups');
    expect(markdown).toContain('- Memory (Filter 1): solved by progress · May return later');
    expect(markdown).toContain('- v1 · Filter 1/5: Time: pain point');
    expect(markdown).toContain('## AI suggestions');
    expect(markdown).toContain('- Core question: Revised question');
  });

  it('escapes learner text so it cannot reshape the document', () => {
    expect(escapeMarkdown('# Title\n- item | [link](x) *bold*')).toBe('\\# Title \\- item \\| \\[link\\]\\(x\\) \\*bold\\*');
    const markdown = topicCardToMarkdown({ stage: 0, version: 0, card: { ...empty, pain_point: '## injected' }, pending: null, history: [] }, t as never);
    expect(markdown).toContain('\\#\\# injected');
    expect(markdown.split('\n').filter((line) => line.startsWith('## '))).not.toContain('## injected');
  });

  it('exports an empty card', () => {
    const markdown = topicCardToMarkdown({ stage: 0, version: 0, card: empty, pending: null, history: [] }, t as never);
    expect(markdown).toContain('- Progress: Pain point');
    expect(markdown.match(/^—$/gm)?.length).toBe(7);
  });
});
