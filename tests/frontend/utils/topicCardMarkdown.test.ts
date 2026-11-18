import { describe, expect, it } from 'vitest';
import { escapeMarkdown, topicCardToMarkdown } from '@/utils/topicCardMarkdown';

const labels: Record<string, string> = {
  topicCardTitle: 'Topic card', topicCardProgress: 'Progress', topicCardVersion: 'Version v{n}',
  topicCardStageFilter: 'Stage {n}', topicCardStageDone: 'Done', topicCardDone: 'You have been through all five stages',
  topicStageTitle1: 'Notice a pain point, then diverge', topicStageTitle4: 'How will you show it?',
  topicCardFeasibility: 'Feasibility check', topicFeasTime: 'Time', topicFeasData: 'Data and setting',
  topicFeasAdvisor: 'Advisor and method', topicFeasPriorWork: 'Done before?', topicFeasOk: 'OK',
  topicFeasUnsure: 'Not sure yet', topicFeasBlocked: 'Difficult', topicFeasMissing: 'Not discussed yet', topicFeasEthics: 'Research ethics', topicCardAiProposed: 'AI-proposed',
  topicCardPainPoint: 'What you are stuck on', topicCardMotherQuestion: 'What you really want to know',
  topicCardCandidates: 'Candidate topics', topicCardOperationalization: 'How you will show it',
  topicCardMeasureMissing: 'No evidence chosen yet', topicCardDiscarded: 'Set-aside topics',
  topicCardDiscardedBy: 'dropped at stage {n}', topicCardCanReturn: 'may return later', topicCardObjections: 'My objections',
  topicCardHistory: 'History', topicCardPending: 'AI draft (not adopted yet)',
};
const t = (key: string, params?: Record<string, string | number>) => Object.entries(params ?? {})
  .reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), labels[key] ?? key);

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };

describe('topic card Markdown', () => {
  it('exports every section in plain language, the current stage goal, and the history', () => {
    const markdown = topicCardToMarkdown({
      stage: 4, version: 4,
      card: {
        pain_point: 'AREQA feels like Gemini', mother_question: 'How do AI replies shape reasoning',
        candidates: ['Reply strategy', 'Question balance'], ai_candidates: ['Question balance'], operationalization: [{ term: 'Depth', measure: '' }, { term: 'Engagement', measure: 'follow-ups' }],
        discarded: [{ topic: 'Memory', filter: 1, reason: 'solved by progress', can_return: true }],
        feasibility: [{ key: 'data', status: 'blocked', note: 'Korean sources' }],
        objections: ['Too many questions annoy me'],
      },
      pending: { card: { ...empty, pain_point: 'AREQA feels like Gemini', mother_question: 'Revised question' }, notes: ['revised'] },
      history: [{ version: 1, stage: 1, note: 'pain point', confirmed_at: 1 }],
    }, t as never);

    expect(markdown).toContain('- Progress: Stage 4');
    expect(markdown).toContain('- How will you show it?');
    expect(markdown).toContain('- Depth: ⚠️ No evidence chosen yet');
    expect(markdown).toContain('- Data and setting: ❌ Difficult · Korean sources');
    expect(markdown).toContain('- Time: ⚠️ Not discussed yet');
    expect(markdown).toContain('- Research ethics: ⚠️ Not discussed yet');
    expect(markdown).toContain('- Question balance (AI-proposed)');
    expect(markdown).toContain('- Reply strategy\n');
    expect(markdown).toContain('- Engagement: follow\\-ups');
    expect(markdown).toContain('- Memory (dropped at stage 1): solved by progress · may return later');
    expect(markdown).toContain('- v1 · Stage 1: pain point');
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

  it('exports an empty card from stage 1, reading old stage 0 as stage 1', () => {
    const markdown = topicCardToMarkdown({ stage: 0, version: 0, card: empty, pending: null, history: [] }, t as never);
    expect(markdown).toContain('- Progress: Stage 1');
    expect(markdown).toContain('- Notice a pain point, then diverge');
    expect(markdown.match(/^—$/gm)?.length).toBe(8);
  });
});
