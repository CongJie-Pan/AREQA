import { describe, expect, it } from 'vitest';
import { escapeMarkdown, topicCardToMarkdown } from '@/utils/topicCardMarkdown';

const labels: Record<string, string> = {
  topicCardTitle: 'Topic card', topicCardProgress: 'Progress', topicCardVersion: 'Version v{n}',
  topicCardStageStart: 'Starting point', topicCardStageFilter: 'Step {n} of 5', topicCardStageDone: 'Done',
  topicCardCurrentQuestion: 'This step asks:', topicCardDone: 'You have confirmed all five questions',
  topicStageQ0: 'What are you stuck on?', topicStageQ4: 'For each key term, what evidence will show it?',
  topicCardPainPoint: 'What you are stuck on', topicCardMotherQuestion: 'What you really want to know',
  topicCardCandidates: 'Candidate topics', topicCardOperationalization: 'How you will show it',
  topicCardMeasureMissing: 'No evidence chosen yet', topicCardDiscarded: 'Set-aside topics',
  topicCardDiscardedBy: 'dropped at step {n}', topicCardCanReturn: 'may return later', topicCardObjections: 'My objections',
  topicCardHistory: 'History', topicCardPending: 'AI draft (not adopted yet)',
};
const t = (key: string, params?: Record<string, string | number>) => Object.entries(params ?? {})
  .reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), labels[key] ?? key);

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };

describe('topic card Markdown', () => {
  it('exports every section in plain language, the current question, and the history', () => {
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

    expect(markdown).toContain('- Progress: Step 4 of 5');
    expect(markdown).toContain('- This step asks: For each key term, what evidence will show it?');
    expect(markdown).toContain('- Depth: ❗ No evidence chosen yet');
    expect(markdown).toContain('- Engagement: follow\\-ups');
    expect(markdown).toContain('- Memory (dropped at step 1): solved by progress · may return later');
    expect(markdown).toContain('- v1 · Step 1 of 5: pain point');
    expect(markdown).toContain('## AI draft (not adopted yet)');
    expect(markdown).toContain('- What you really want to know: Revised question');
    expect(markdown).not.toMatch(/Filter|Measurable|Simplest fix/);
  });

  it('escapes learner text so it cannot reshape the document', () => {
    expect(escapeMarkdown('# Title\n- item | [link](x) *bold*')).toBe('\\# Title \\- item \\| \\[link\\]\\(x\\) \\*bold\\*');
    const markdown = topicCardToMarkdown({ stage: 0, version: 0, card: { ...empty, pain_point: '## injected' }, pending: null, history: [] }, t as never);
    expect(markdown).toContain('\\#\\# injected');
    expect(markdown.split('\n').filter((line) => line.startsWith('## '))).not.toContain('## injected');
  });

  it('exports an empty card from the starting point', () => {
    const markdown = topicCardToMarkdown({ stage: 0, version: 0, card: empty, pending: null, history: [] }, t as never);
    expect(markdown).toContain('- Progress: Starting point');
    expect(markdown).toContain('- This step asks: What are you stuck on?');
    expect(markdown.match(/^—$/gm)?.length).toBe(7);
  });
});
