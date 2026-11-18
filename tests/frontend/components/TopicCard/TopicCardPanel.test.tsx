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
const fullCard = {
  pain_point: '系統和 Gemini 差不多', mother_question: 'AI 的答覆如何影響思辨',
  candidates: ['回覆策略與反思深度'],
  operationalization: [{ term: '反思深度', measure: '' }, { term: '認知投入', measure: '追問次數' }],
  discarded: [{ topic: '記憶機制', filter: 1, reason: '技術會自動解決', can_return: true }],
  objections: ['一直被問會煩'],
};

function renderPanel(overrides: Partial<UseTopicCardResult> = {}, onClose?: () => void, onExploreCandidate?: (candidate: string) => void) {
  const topicCard: UseTopicCardResult = {
    state: state(), failure: null, isConfirming: false, confirm: vi.fn().mockResolvedValue('advanced'), reload: vi.fn(),
    ...overrides,
  };
  render(<UserPreferencesProvider><App><TopicCardPanel topicCard={topicCard} onClose={onClose} onExploreCandidate={onExploreCandidate} /></App></UserPreferencesProvider>);
  return topicCard;
}

describe('TopicCardPanel', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('shows only the current step as a plain-language question, with an optional why', () => {
    renderPanel({ state: state({ stage: 1, version: 1 }) });

    expect(screen.getByText('第 1 關／共 5 關')).toBeInTheDocument();
    expect(screen.getByText('這個問題，過兩年技術進步後還存在嗎？')).toBeInTheDocument();
    expect(screen.queryByText('有沒有一個很簡單的做法，現在就能解決它？')).not.toBeInTheDocument();
    expect(screen.getByText('為什麼要問這個？')).toBeInTheDocument();
    expect(screen.getByText(/它比較像產品功能，不像研究題目/)).toBeInTheDocument();
    // No filter jargon.
    expect(screen.queryByText(/Measurable|Simplest fix|篩子/)).not.toBeInTheDocument();
  });

  it('opens fields at the step that asks about them', () => {
    renderPanel({ state: state({ stage: 1, version: 1, card: fullCard }) });
    expect(screen.getByText('系統和 Gemini 差不多')).toBeInTheDocument();
    expect(screen.queryByText('AI 的答覆如何影響思辨')).not.toBeInTheDocument();
    expect(screen.queryByText(/怎麼證明/)).not.toBeInTheDocument();
  });

  it('shows measures from step 4 and marks terms without evidence', () => {
    renderPanel({ state: state({ stage: 4, version: 4, card: fullCard }) });

    expect(screen.getByText('第 4 關／共 5 關')).toBeInTheDocument();
    expect(screen.getByText('AI 的答覆如何影響思辨')).toBeInTheDocument();
    expect(screen.getByText('怎麼證明（每個關鍵詞用什麼證據看）')).toBeInTheDocument();
    expect(screen.getByText(/還沒想好用什麼證據/)).toBeInTheDocument();
    expect(screen.getByText('追問次數')).toBeInTheDocument();
    expect(screen.getByText('淘汰的題目 (1)')).toBeInTheDocument();
    expect(screen.getByText('第 1 關淘汰 · 技術會自動解決 · 之後可以再回來')).toBeInTheDocument();
    expect(screen.getByText('我的反問 (1)')).toBeInTheDocument();
    expect(screen.getByText('版本 v4')).toBeInTheDocument();
  });

  it('puts the AI draft right above the action and shows only what changed', () => {
    renderPanel({ state: state({
      card: { ...empty, pain_point: '已確認的痛點' },
      pending: { card: { ...empty, pain_point: '已確認的痛點', candidates: ['候選 A', '候選 B'] }, notes: ['加入候選'] },
    }) });

    const draft = screen.getByRole('note');
    expect(draft).toHaveTextContent('AI 根據剛才的對話，幫你整理成：');
    expect(draft).toHaveTextContent('候選 A');
    expect(draft).not.toHaveTextContent('已確認的痛點');
    expect(screen.getByRole('button', { name: '對，就這樣，進入下一關' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '我再想想' })).toBeInTheDocument();
  });

  it('hides draft fields from later steps even if they arrive', () => {
    renderPanel({ state: state({
      pending: { card: { ...empty, pain_point: '痛點', operationalization: [{ term: '聯盟形成動機', measure: '制衡與扈從' }] }, notes: [] },
    }) });
    expect(screen.queryByText('聯盟形成動機')).not.toBeInTheDocument();
  });

  it('explains how to revise a draft', () => {
    renderPanel({ state: state({ pending: { card: { ...empty, pain_point: '草稿' }, notes: [] } }) });
    fireEvent.click(screen.getByRole('button', { name: '我再想想' }));
    expect(screen.getByText('直接在對話裡告訴 AI 要改哪裡，它會更新這份草稿。')).toBeInTheDocument();
  });

  it('advances through the hook, also without a draft, and disables while confirming', async () => {
    const topicCard = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '這一關我想清楚了，進入下一關' }));
    await waitFor(() => expect(topicCard.confirm).toHaveBeenCalledTimes(1));

    renderPanel({ isConfirming: true });
    expect(screen.getAllByRole('button', { name: '這一關我想清楚了，進入下一關' })[1]).toBeDisabled();
  });

  it('explains stale confirmations and keeps the card', async () => {
    renderPanel({ confirm: vi.fn().mockResolvedValue('stale') });
    fireEvent.click(screen.getByRole('button', { name: '這一關我想清楚了，進入下一關' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('題目卡已有更新');
  });

  it('shows failure messages and the completed state', () => {
    renderPanel({ state: null, failure: 'not_synced' });
    expect(screen.getByRole('status')).toHaveTextContent('對話同步完成後即可使用題目卡');

    renderPanel({ state: state({ stage: 6, version: 6 }) });
    expect(screen.getByText('五個問題都已由你確認')).toBeInTheDocument();
    expect(screen.queryAllByRole('button', { name: /進入下一關/ })).toHaveLength(0);
  });

  it('offers branch exploration per confirmed candidate', () => {
    const onExplore = vi.fn();
    renderPanel({ state: state({ card: { ...empty, candidates: ['候選 A', '候選 B'] } }) }, undefined, onExplore);
    fireEvent.click(screen.getByRole('button', { name: '開分支探索：候選 B' }));
    expect(onExplore).toHaveBeenCalledWith('候選 B');
  });

  it('downloads the card as Markdown and closes on request', async () => {
    const createObjectURL = vi.fn(() => 'blob:card');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const onClose = vi.fn();
    renderPanel({ state: state({ version: 3, card: { ...empty, pain_point: '痛點文字' } }) }, onClose);

    fireEvent.click(screen.getByRole('button', { name: '匯出 Markdown' }));
    const blob = (createObjectURL.mock.calls[0] as unknown as [Blob])[0];
    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(blob);
    });
    expect(text).toContain('痛點文字');
    click.mockRestore();

    fireEvent.click(screen.getByRole('button', { name: '收合題目卡' }));
    expect(onClose).toHaveBeenCalled();
  });
});
