import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TopicStageNudge } from '@/components/TopicCard/StageNudge';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import type { UseTopicCardResult } from '@/hooks/useTopicCard';
import type { TopicCardState } from '@/services/topicCard';

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };

function renderNudge(state: Partial<TopicCardState> | null, props: { isStreaming?: boolean; disabled?: boolean } = {}) {
  const onSend = vi.fn().mockResolvedValue(undefined);
  const topicCard = {
    state: state && { stage: 3, version: 1, card: empty, pending: null, history: [], ...state },
    failure: null, isSaving: false, adopt: vi.fn(), reject: vi.fn(), goToStage: vi.fn(), skipFocus: vi.fn(), reload: vi.fn(),
  } as UseTopicCardResult;
  const view = render(
    <UserPreferencesProvider>
      <TopicStageNudge topicCard={topicCard} isStreaming={props.isStreaming ?? false} disabled={props.disabled} onSend={onSend} />
    </UserPreferencesProvider>,
  );
  return { onSend, view };
}

describe('TopicStageNudge', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('offers the next stage and sends the move as the learner', () => {
    const { onSend } = renderNudge({ stage: 3, next_stage: 4 });
    fireEvent.click(screen.getByRole('button', { name: '前往第 4 階段：幫候選題目找「看得見的證據」' }));
    expect(onSend).toHaveBeenCalledWith('好，我們進到第 4 階段：幫候選題目找「看得見的證據」');
    // Hidden until the card reloads at the new stage.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers to wrap up after stage 5', () => {
    const { onSend } = renderNudge({ stage: 5, next_stage: 6 });
    fireEvent.click(screen.getByRole('button', { name: '五個階段都談完了：整理最終題目' }));
    expect(onSend).toHaveBeenCalledWith('好，五個階段都談完了，幫我整理最終題目');
  });

  it.each([
    ['no card', null, {}],
    ['not ready', { stage: 3, next_stage: null }, {}],
    ['older backend', { stage: 3 }, {}],
    ['streaming', { stage: 3, next_stage: 4 }, { isStreaming: true }],
  ])('stays hidden: %s', (_name, state, props) => {
    renderNudge(state as Partial<TopicCardState> | null, props);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('is disabled while sending is not possible', () => {
    renderNudge({ stage: 3, next_stage: 4 }, { disabled: true });
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
