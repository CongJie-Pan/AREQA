import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TopicCardPanel } from '@/components/TopicCard';
import { UserPreferencesProvider } from '@/contexts/UserPreferencesContext';
import type { UseTopicCardResult } from '@/hooks/useTopicCard';
import type { TopicCardState } from '@/services/topicCard';

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };
const state = (overrides: Partial<TopicCardState> = {}): TopicCardState => ({
  stage: 0, version: 0, card: empty, pending: null, history: [], ...overrides,
});

function renderPanel(overrides: Partial<UseTopicCardResult> = {}, onClose?: () => void) {
  const topicCard: UseTopicCardResult = {
    state: state(), failure: null, isConfirming: false, confirm: vi.fn().mockResolvedValue('advanced'), reload: vi.fn(),
    ...overrides,
  };
  render(<UserPreferencesProvider><App><TopicCardPanel topicCard={topicCard} onClose={onClose} /></App></UserPreferencesProvider>);
  return topicCard;
}

describe('TopicCardPanel', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('renders the card sections and marks measures that are still missing', () => {
    renderPanel({ state: state({ stage: 4, version: 4, card: {
      pain_point: '系統和 Gemini 差不多', mother_question: 'AI 的答覆如何影響思辨',
      candidates: ['回覆策略與反思深度'],
      operationalization: [{ term: '反思深度', measure: '' }, { term: '認知投入', measure: '追問次數' }],
      discarded: [{ topic: '記憶機制', filter: 1, reason: '技術會自動解決', can_return: true }],
      objections: ['一直被問會煩'],
    } }) });

    expect(screen.getByText('系統和 Gemini 差不多')).toBeInTheDocument();
    expect(screen.getByText('AI 的答覆如何影響思辨')).toBeInTheDocument();
    expect(screen.getByText(/尚未填測量方式/)).toBeInTheDocument();
    expect(screen.getByText('追問次數')).toBeInTheDocument();
    expect(screen.getByText(/記憶機制/)).toBeInTheDocument();
    expect(screen.getByText(/篩子 1 · 技術會自動解決 · 可降級保留/)).toBeInTheDocument();
    expect(screen.getByText('一直被問會煩')).toBeInTheDocument();
    expect(screen.getByText('版本 v4')).toBeInTheDocument();
    expect(screen.getByText('4. 可測').closest('li')).toHaveAttribute('aria-current', 'step');
  });

  it('labels AI proposals as suggestions until the learner confirms', () => {
    renderPanel({ state: state({ pending: { card: { ...empty, pain_point: '草稿痛點' }, notes: ['加入痛點'] } }) });
    expect(screen.getByRole('note')).toHaveTextContent('確認這一關時才會採用');
    expect(screen.getByRole('note')).toHaveTextContent('加入痛點');
    expect(screen.getByText('草稿痛點')).toBeInTheDocument();
  });

  it('confirms through the hook and disables the button while confirming', async () => {
    const topicCard = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '我確認這一關過了' }));
    await waitFor(() => expect(topicCard.confirm).toHaveBeenCalledTimes(1));

    renderPanel({ isConfirming: true });
    expect(screen.getAllByRole('button', { name: '我確認這一關過了' })[1]).toBeDisabled();
  });

  it('explains stale and failed confirmations and keeps the card', async () => {
    renderPanel({ confirm: vi.fn().mockResolvedValue('stale') });
    fireEvent.click(screen.getByRole('button', { name: '我確認這一關過了' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('題目卡已有更新');
  });

  it('shows failure messages and the completed state', () => {
    renderPanel({ state: null, failure: 'not_synced' });
    expect(screen.getByRole('status')).toHaveTextContent('對話同步完成後即可使用題目卡');

    renderPanel({ state: state({ stage: 6, version: 6 }) });
    expect(screen.getByText('五道篩子都已由你確認')).toBeInTheDocument();
    expect(screen.queryAllByRole('button', { name: '我確認這一關過了' })).toHaveLength(0);
  });

  it('closes on request', () => {
    const onClose = vi.fn();
    renderPanel({}, onClose);
    fireEvent.click(screen.getByRole('button', { name: '收合題目卡' }));
    expect(onClose).toHaveBeenCalled();
  });
});
