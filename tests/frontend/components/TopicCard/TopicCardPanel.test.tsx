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
  stage: 1, version: 0, card: empty, pending: null, history: [], ...overrides,
});
const fullCard = {
  pain_point: '系統和 Gemini 差不多', mother_question: 'AI 的答覆如何影響思辨',
  candidates: ['回覆策略與反思深度'],
  operationalization: [{ term: '反思深度', measure: '' }, { term: '認知投入', measure: '追問次數' }],
  discarded: [{ topic: '記憶機制', filter: 2, reason: '現成工具已解決', can_return: true }],
  objections: ['一直被問會煩'],
};

function renderPanel(overrides: Partial<UseTopicCardResult> = {}, onClose?: () => void, onExploreCandidate?: (candidate: string) => void) {
  const topicCard: UseTopicCardResult = {
    state: state(), failure: null, isSaving: false,
    adopt: vi.fn().mockResolvedValue('adopted'), goToStage: vi.fn().mockResolvedValue(true),
    skipFocus: vi.fn().mockResolvedValue(true), reload: vi.fn(),
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

  it('shows the stage, its one-line goal and subtitle, without the old question block', () => {
    renderPanel({ state: state({ stage: 2 }) });

    expect(screen.getByText('第 2 階段')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '有沒有很簡單的解法？' })).toBeInTheDocument();
    expect(screen.getByText(/一個現成工具、現有論文或研究成果/)).toBeInTheDocument();
    expect(screen.queryByText(/這一關要回答|為什麼要問這個|關／共/)).not.toBeInTheDocument();
  });

  it('lets the learner jump to any stage from the stepper', async () => {
    const topicCard = renderPanel({ state: state({ stage: 1 }) });
    const current = screen.getByRole('button', { name: '切換到第 1 階段：觀察痛點，先發散' });
    expect(current).toHaveAttribute('aria-current', 'step');

    fireEvent.click(screen.getByRole('button', { name: '切換到第 4 階段：怎麼證明？' }));
    await waitFor(() => expect(topicCard.goToStage).toHaveBeenCalledWith(4));
    fireEvent.click(current);
    expect(topicCard.goToStage).toHaveBeenCalledTimes(1);
  });

  it('moves to the next stage without a draft, and keeps that action quieter when a draft is shown', async () => {
    const topicCard = renderPanel({ state: state({ stage: 3 }) });
    fireEvent.click(screen.getByRole('button', { name: '下一階段 →' }));
    await waitFor(() => expect(topicCard.goToStage).toHaveBeenCalledWith(4));
    expect(screen.queryByRole('button', { name: '採用這份整理' })).not.toBeInTheDocument();
  });

  it('opens fields at their stage, but keeps fields that already have content', () => {
    renderPanel({ state: state({ stage: 1, card: { ...fullCard, operationalization: [] } }) });
    expect(screen.getByText('系統和 Gemini 差不多')).toBeInTheDocument();
    // Jumped back from stage 3: the mother question stays visible.
    expect(screen.getByText('AI 的答覆如何影響思辨')).toBeInTheDocument();
    expect(screen.queryByText(/怎麼證明（/)).not.toBeInTheDocument();
    expect(screen.queryByText('可行性檢查')).not.toBeInTheDocument();
  });

  it('shows measures from stage 4 and marks terms without evidence with ⚠️', () => {
    renderPanel({ state: state({ stage: 4, version: 4, card: fullCard }) });

    expect(screen.getByText('怎麼證明（每個關鍵詞用什麼證據看）')).toBeInTheDocument();
    expect(screen.getByText('⚠️ 還沒想好用什麼證據')).toBeInTheDocument();
    expect(screen.getByText('追問次數')).toBeInTheDocument();
    expect(screen.getByText('淘汰的題目 (1)')).toBeInTheDocument();
    expect(screen.getByText('第 2 階段淘汰 · 現成工具已解決 · 之後可以再回來')).toBeInTheDocument();
    expect(screen.getByText('我的反問 (1)')).toBeInTheDocument();
    expect(screen.getByText('版本 v4')).toBeInTheDocument();
  });

  it('shows the five feasibility checks at stage 5, including ethics, with unanswered ones marked', () => {
    renderPanel({ state: state({ stage: 5, card: { ...fullCard, feasibility: [
      { key: 'data', status: 'blocked', note: '韓文資料讀不懂' }, { key: 'time', status: 'ok', note: '' },
    ] } }) });

    expect(screen.getByText('可行性檢查')).toBeInTheDocument();
    const rows = document.querySelectorAll('.areqa-topic-card-feasibility li');
    expect([...rows].map((row) => row.getAttribute('data-status'))).toEqual(['ok', 'blocked', 'missing', 'missing', 'missing']);
    expect(screen.getByText('研究倫理')).toBeInTheDocument();
    expect(screen.getByText('韓文資料讀不懂')).toBeInTheDocument();
    expect(screen.getAllByText('⚠️ 還沒討論')).toHaveLength(3);
    expect(screen.getByText('❌ 有困難')).toBeInTheDocument();
  });

  it('shows AI search hints at stage 1 and copies a keyword', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    renderPanel({ state: state({ suggestions: { keywords: ['韓國 避險外交'], gaps: ['國內因素的作用是否被低估？'], related: ['日韓關係'] } }) });

    expect(screen.getByText('AI 建議（參考用，請自己查證）')).toBeInTheDocument();
    expect(screen.getByText('國內因素的作用是否被低估？')).toBeInTheDocument();
    expect(screen.getByText('日韓關係')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '複製關鍵字：韓國 避險外交' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('韓國 避險外交'));
  });

  it('keeps only keywords at stage 2 and hides hints from stage 3', () => {
    const suggestions = { keywords: ['hedging South Korea'], gaps: ['缺口？'], related: ['相關'] };
    renderPanel({ state: state({ stage: 2, suggestions }) });
    expect(screen.getByText('hedging South Korea')).toBeInTheDocument();
    expect(screen.queryByText('缺口？')).not.toBeInTheDocument();

    renderPanel({ state: state({ stage: 3, suggestions }) });
    expect(screen.getAllByText('hedging South Korea')).toHaveLength(1);
  });

  it('puts the AI draft right above the actions and shows only what changed', async () => {
    const topicCard = renderPanel({ state: state({
      card: { ...empty, pain_point: '已確認的痛點' },
      pending: { card: { ...empty, pain_point: '已確認的痛點', candidates: ['候選 A', '候選 B'] }, notes: ['加入候選'] },
    }) });

    const draft = screen.getByRole('note');
    expect(draft).toHaveTextContent('AI 根據剛才的對話，幫你整理成：');
    expect(draft).toHaveTextContent('候選 A');
    expect(draft).not.toHaveTextContent('已確認的痛點');
    expect(screen.getByRole('button', { name: '我再想想' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一階段 →' })).toHaveClass('areqa-topic-card-next');

    fireEvent.click(screen.getByRole('button', { name: '採用這份整理' }));
    await waitFor(() => expect(topicCard.adopt).toHaveBeenCalledTimes(1));
    expect(topicCard.goToStage).not.toHaveBeenCalled();
  });

  it('hides draft fields from later stages even if they arrive', () => {
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

  it('disables the actions while saving', () => {
    renderPanel({ isSaving: true, state: state({ pending: { card: { ...empty, pain_point: '草稿' }, notes: [] } }) });
    expect(screen.getByRole('button', { name: '採用這份整理' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '下一階段 →' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '切換到第 2 階段：有沒有很簡單的解法？' })).toBeDisabled();
  });

  it('explains stale adoption and failed stage changes', async () => {
    renderPanel({
      adopt: vi.fn().mockResolvedValue('stale'),
      state: state({ pending: { card: { ...empty, pain_point: '草稿' }, notes: [] } }),
    });
    fireEvent.click(screen.getByRole('button', { name: '採用這份整理' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('題目卡已有更新');

    renderPanel({ goToStage: vi.fn().mockResolvedValue(false) });
    fireEvent.click(screen.getAllByRole('button', { name: '下一階段 →' }).at(-1)!);
    expect(await screen.findByText('切換階段失敗，請稍後再試。')).toBeInTheDocument();
  });

  it('shows failure messages and the completed state', () => {
    renderPanel({ state: null, failure: 'not_synced' });
    expect(screen.getByRole('status')).toHaveTextContent('對話同步完成後即可使用題目卡');

    renderPanel({ state: state({ stage: 6, version: 6 }) });
    expect(screen.getByText('你已走完五個階段')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '下一階段 →' })).not.toBeInTheDocument();
    // The stepper still lets the learner revisit any stage.
    expect(screen.getByRole('button', { name: '切換到第 3 階段：你真正想知道的是什麼？' })).toBeEnabled();
  });

  it('tags candidates the AI proposed, in the draft and on the card', () => {
    renderPanel({ state: state({
      card: { ...empty, candidates: ['AI 列的題目', '我自己的題目'], ai_candidates: ['AI 列的題目'] },
      pending: { card: { ...empty, candidates: ['AI 新題目'], ai_candidates: ['AI 新題目'] }, notes: [] },
    }) });
    const tags = screen.getAllByText('AI 提議');
    expect(tags).toHaveLength(2);
    expect(tags[0]).toHaveAttribute('title', '這個候選是 AI 列出的；用你自己的話改寫後，就會變成你的想法。');
    expect(screen.getByText('我自己的題目').parentElement).not.toHaveTextContent('AI 提議');
  });

  it('offers branch exploration per adopted candidate', () => {
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
  it('shows the coach focus quietly and lets the learner set it aside', async () => {
    const focus = { id: 'measure:3fa2b1c09d8e', kind: 'measure' as const, term: '反思深度' };
    const topicCard = renderPanel({ state: state({ stage: 4, card: fullCard, focus }) });

    expect(screen.getByText('這輪先看：「反思深度」要用什麼證據看出來')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '換一個' }));
    await waitFor(() => expect(topicCard.skipFocus).toHaveBeenCalledWith(focus.id));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('names feasibility focus items with their label, not the internal key', () => {
    renderPanel({ state: state({ stage: 5, focus: { id: 'feasibility_unsure:ethics', kind: 'feasibility_unsure', term: 'ethics' } }) });
    expect(screen.getByText('這輪先看：可行性：研究倫理還缺什麼才能確定')).toBeInTheDocument();
    expect(screen.queryByText(/ethics/)).not.toBeInTheDocument();
  });

  it('reports a failed set-aside without losing the card', async () => {
    const focus = { id: 'mother_question', kind: 'mother_question' as const, term: '' };
    renderPanel({ state: state({ stage: 3, focus }), skipFocus: vi.fn().mockResolvedValue(false) });
    fireEvent.click(screen.getByRole('button', { name: '換一個' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('暫時無法更換，請稍後再試。');
    expect(screen.getByText('這輪先看：拿掉工具和案例，你真正想知道什麼')).toBeInTheDocument();
  });

  it('shows the pending check-back instead of the focus after a revision', () => {
    const focus = { id: 'mother_question', kind: 'mother_question' as const, term: '' };
    renderPanel({ state: state({
      stage: 3, focus, review: { version: 3, changed: ['mother_question'], stages: [2, 4], created_at: 1 },
    }) });
    expect(screen.getByText('你剛改了題目，教練下一輪會先陪你回頭看第 2、4 階段還成不成立。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '換一個' })).not.toBeInTheDocument();
  });

  it('shows no focus line for older backends or when the topic is done', () => {
    renderPanel({ state: state({ stage: 6, focus: { id: 'candidates', kind: 'candidates', term: '' } }) });
    expect(screen.queryByText(/這輪先看/)).not.toBeInTheDocument();
  });
});
