import React from 'react';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
    adopt: vi.fn().mockResolvedValue('adopted'), reject: vi.fn().mockResolvedValue('rejected'),
    goToStage: vi.fn().mockResolvedValue(true), reload: vi.fn(),
    ...overrides,
  };
  render(<UserPreferencesProvider><App><TopicCardPanel topicCard={topicCard} onClose={onClose} onExploreCandidate={onExploreCandidate} /></App></UserPreferencesProvider>);
  return topicCard;
}

const otherRecords = () => screen.getByText('其他紀錄').closest('details')!;

describe('TopicCardPanel', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('shows the stage, its goal and subtitle, and leaves steering to the conversation', () => {
    renderPanel({ state: state({ stage: 2 }) });

    expect(screen.getByText('第 2 階段')).toHaveClass('areqa-topic-card-step-label');
    expect(screen.getByRole('heading', { name: '有沒有很簡單的解法？' })).toBeInTheDocument();
    expect(screen.getByText(/一個現成工具、現有論文或研究成果/)).toHaveClass('areqa-topic-card-subtitle');
    // No hint text, focus line, or next-stage button on the card.
    expect(screen.queryByText(/要不要採用、何時換階段都由你決定/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /下一階段/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/這輪先看/)).not.toBeInTheDocument();
  });

  it('lets the learner jump to any stage from the stepper', async () => {
    const topicCard = renderPanel({ state: state({ stage: 1 }) });
    const current = screen.getByRole('button', { name: '切換到第 1 階段：觀察痛點，先發散' });
    expect(current).toHaveAttribute('aria-current', 'step');

    fireEvent.click(screen.getByRole('button', { name: '切換到第 4 階段：幫候選題目找「看得見的證據」' }));
    await waitFor(() => expect(topicCard.goToStage).toHaveBeenCalledWith(4));
    fireEvent.click(current);
    expect(topicCard.goToStage).toHaveBeenCalledTimes(1);
  });

  it('heads the card with the mother question, falling back to the pain point', () => {
    renderPanel({ state: state({ stage: 3, card: fullCard }) });
    expect(document.querySelector('.areqa-topic-card-headline')).toHaveTextContent('AI 的答覆如何影響思辨');
    expect(document.querySelector('.areqa-topic-card-subline')).toHaveTextContent('系統和 Gemini 差不多');

    renderPanel({ state: state({ stage: 1, card: { ...empty, pain_point: '只寫了痛點' } }) });
    expect(screen.getByText('只寫了痛點')).toHaveClass('areqa-topic-card-headline');

    renderPanel({ state: state() });
    expect(screen.getByText('還沒有內容。在對話裡說說你卡在哪裡，AI 整理好後會請你確認。')).toBeInTheDocument();
  });

  it('keeps only the current stage field open and folds the rest into one line', () => {
    renderPanel({ state: state({ stage: 4, version: 4, card: fullCard, history: [{ version: 4, stage: 4, note: '加入關鍵詞', confirmed_at: 1 }] }) });

    const field = screen.getByRole('region', { name: '看得見的證據' });
    expect(field).toHaveTextContent('⚠️ 還沒想好用什麼證據');
    expect(field).toHaveTextContent('追問次數');
    expect(field).not.toHaveTextContent('回覆策略與反思深度');

    const more = otherRecords();
    expect(more).not.toHaveAttribute('open');
    expect(more.querySelector('summary')).toHaveTextContent('其他紀錄候選題目 · 淘汰 1 · 反問 1 · 版本 1');
    expect(within(more).getByText('第 2 階段淘汰 · 現成工具已解決 · 之後可以再回來')).toBeInTheDocument();
    expect(within(more).getByText('一直被問會煩')).toBeInTheDocument();
    const groupLabels = [...more.querySelectorAll('.areqa-topic-card-group-label')].map((label) => label.textContent);
    expect(groupLabels).toEqual(['候選題目', '淘汰的題目1', '我的反問1', '版本紀錄1']);
    const history = more.querySelector('.areqa-topic-card-history li')!;
    expect(history).toHaveTextContent('v4加入關鍵詞第 4 階段');
    expect(screen.getByText('版本 v4')).toBeInTheDocument();
  });

  it('shows the five feasibility checks at stage 5, including ethics, with unanswered ones marked', () => {
    renderPanel({ state: state({ stage: 5, card: { ...fullCard, feasibility: [
      { key: 'data', status: 'blocked', note: '韓文資料讀不懂' }, { key: 'time', status: 'ok', note: '' },
    ] } }) });

    const field = screen.getByRole('region', { name: '可行性檢查' });
    const rows = field.querySelectorAll('.areqa-topic-card-feasibility li');
    expect([...rows].map((row) => row.getAttribute('data-status'))).toEqual(['ok', 'blocked', 'missing', 'missing', 'missing']);
    expect(within(field).getByText('研究倫理')).toBeInTheDocument();
    expect(within(field).getByText('韓文資料讀不懂')).toBeInTheDocument();
    expect(within(field).getAllByText('⚠️ 還沒討論')).toHaveLength(3);
    expect(within(field).getByText('❌ 有困難')).toBeInTheDocument();
  });

  it('shows copyable search keywords only in stages 1 and 2', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    const suggestions = { keywords: ['韓國 避險外交'], gaps: ['國內因素的作用是否被低估？'], related: ['日韓關係'] };
    renderPanel({ state: state({ stage: 2, suggestions }) });

    fireEvent.click(screen.getByRole('button', { name: '複製關鍵字：韓國 避險外交' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('韓國 避險外交'));
    // Possible gaps and related topics are no longer shown on the card.
    expect(screen.queryByText('國內因素的作用是否被低估？')).not.toBeInTheDocument();
    expect(screen.queryByText('日韓關係')).not.toBeInTheDocument();

    renderPanel({ state: state({ stage: 3, suggestions }) });
    expect(screen.getAllByText('韓國 避險外交')).toHaveLength(1);
  });

  it('asks about a candidate draft listing only the new candidates', async () => {
    const topicCard = renderPanel({ state: state({
      card: { ...empty, pain_point: '已確認的痛點', candidates: ['舊候選'] },
      pending: { card: { ...empty, pain_point: '已確認的痛點', candidates: ['舊候選', '候選 A'], ai_candidates: ['候選 A'] }, notes: ['加入候選'] },
    }) });

    const draft = screen.getByRole('group', { name: 'AI 幫你整理了以下候選題目，要加入題目卡的候選清單嗎？' });
    expect(within(draft).getByText('候選 A')).toBeInTheDocument();
    expect(within(draft).getByText('AI 提議')).toBeInTheDocument();
    expect(draft).not.toHaveTextContent('舊候選');
    expect(draft).not.toHaveTextContent('已確認的痛點');

    fireEvent.click(within(draft).getByRole('button', { name: '需要' }));
    await waitFor(() => expect(topicCard.adopt).toHaveBeenCalledTimes(1));
    expect(topicCard.reject).not.toHaveBeenCalled();
    expect(topicCard.goToStage).not.toHaveBeenCalled();
  });

  it('lists only changed measures, removed candidates, and newly dropped topics', () => {
    renderPanel({ state: state({
      stage: 4,
      card: { ...fullCard },
      pending: { card: {
        ...fullCard,
        candidates: [],
        operationalization: [...fullCard.operationalization, { term: '信任', measure: '' }],
        discarded: [...fullCard.discarded, { topic: '回覆策略與反思深度', filter: 4, reason: '太大', can_return: false }],
      }, notes: [] },
    }) });

    const draft = screen.getByRole('group', { name: 'AI 幫你整理了以下內容，要更新到題目卡嗎？' });
    const lines = [...draft.querySelectorAll('.areqa-topic-card-draft-lines li')].map((line) => line.textContent);
    // The dropped candidate shows once, as a set-aside topic, not also as a removal.
    expect(lines).toEqual(['看得見的證據信任 ⚠️ 還沒想好用什麼證據', '淘汰的題目回覆策略與反思深度（太大）']);
    expect(draft).not.toHaveTextContent('認知投入');
  });

  it('marks a candidate the draft would remove', () => {
    renderPanel({ state: state({
      card: { ...empty, candidates: ['A', 'B'] },
      pending: { card: { ...empty, candidates: ['A'] }, notes: [] },
    }) });
    const line = document.querySelector('.areqa-topic-card-draft-lines li[data-change="remove"]');
    expect(line).toHaveTextContent('從候選題目移除B');
  });

  it('falls back to the draft notes when nothing visible changes', () => {
    renderPanel({ state: state({ pending: { card: { ...empty }, notes: ['整理了反問'] } }) });
    expect(screen.getByRole('group', { name: /要更新到題目卡/ })).toHaveTextContent('整理了反問');
  });

  it('declines the draft with 不需要 and leaves the adopted card alone', async () => {
    const topicCard = renderPanel({ state: state({ pending: { card: { ...empty, candidates: ['候選 A'] }, notes: [] } }) });
    fireEvent.click(screen.getByRole('button', { name: '不需要' }));
    await waitFor(() => expect(topicCard.reject).toHaveBeenCalledTimes(1));
    expect(topicCard.adopt).not.toHaveBeenCalled();
  });

  it('reports a stale or failed decline', async () => {
    renderPanel({
      reject: vi.fn().mockResolvedValue('failed'),
      state: state({ pending: { card: { ...empty, candidates: ['候選 A'] }, notes: [] } }),
    });
    fireEvent.click(screen.getByRole('button', { name: '不需要' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('候選 A')).toBeInTheDocument();
  });

  it('hides draft fields from later stages even if they arrive', () => {
    renderPanel({ state: state({
      pending: { card: { ...empty, pain_point: '痛點', operationalization: [{ term: '聯盟形成動機', measure: '制衡與扈從' }] }, notes: [] },
    }) });
    expect(screen.queryByText(/聯盟形成動機/)).not.toBeInTheDocument();
  });

  it('disables the actions while saving', () => {
    renderPanel({ isSaving: true, state: state({ pending: { card: { ...empty, pain_point: '草稿' }, notes: [] } }) });
    expect(screen.getByRole('button', { name: '需要' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '不需要' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '切換到第 2 階段：有沒有很簡單的解法？' })).toBeDisabled();
  });

  it('explains stale adoption and failed stage changes', async () => {
    renderPanel({
      adopt: vi.fn().mockResolvedValue('stale'),
      state: state({ pending: { card: { ...empty, pain_point: '草稿' }, notes: [] } }),
    });
    fireEvent.click(screen.getByRole('button', { name: '需要' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('題目卡已有更新');

    renderPanel({ goToStage: vi.fn().mockResolvedValue(false) });
    fireEvent.click(screen.getAllByRole('button', { name: '切換到第 3 階段：你真正想知道的是什麼？' }).at(-1)!);
    expect(await screen.findByText('切換階段失敗，請稍後再試。')).toBeInTheDocument();
  });

  it('shows failure messages and the completed state', () => {
    renderPanel({ state: null, failure: 'not_synced' });
    expect(screen.getByRole('status')).toHaveTextContent('對話同步完成後即可使用題目卡');

    renderPanel({ state: state({ stage: 6, version: 6, card: fullCard }) });
    expect(screen.getByText('你已走完五個階段')).toBeInTheDocument();
    // Done: no stage field; everything stays reachable under other records.
    expect(screen.queryByRole('region', { name: '候選題目' })).not.toBeInTheDocument();
    expect(otherRecords().querySelector('summary')).toHaveTextContent('候選題目 · 看得見的證據');
    // The stepper still lets the learner revisit any stage.
    expect(screen.getByRole('button', { name: '切換到第 3 階段：你真正想知道的是什麼？' })).toBeEnabled();
  });

  it('tags candidates the AI proposed, in the draft and on the card', () => {
    renderPanel({ state: state({
      card: { ...empty, candidates: ['AI 列的題目', '我自己的題目'], ai_candidates: ['AI 列的題目'] },
      pending: { card: { ...empty, candidates: ['AI 列的題目', '我自己的題目', 'AI 新題目'], ai_candidates: ['AI 列的題目', 'AI 新題目'] }, notes: [] },
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
});

describe('TopicCardPanel other records', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
  });

  it('lists versions newest first with the stage under each note', () => {
    renderPanel({ state: state({ stage: 3, card: { ...empty, candidates: ['A'] }, history: [
      { version: 1, stage: 1, note: '加入痛點', confirmed_at: 1 },
      { version: 2, stage: 2, note: '', confirmed_at: 2 },
    ] }) });
    const rows = [...document.querySelectorAll('.areqa-topic-card-history li')].map((row) => row.textContent);
    expect(rows).toEqual(['v2—第 2 階段', 'v1加入痛點第 1 階段']);
  });
});
