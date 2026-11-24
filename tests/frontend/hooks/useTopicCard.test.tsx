import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TOPIC_CARD_REFRESH_DELAYS_MS, useTopicCard } from '@/hooks/useTopicCard';
import { useChatStore } from '@/store/chat';
import {
  TopicCardError, adoptTopicCardDraft, fetchTopicCard, setTopicCardStage, skipTopicCardFocus, type TopicCardState,
} from '@/services/topicCard';

vi.mock('@/services/topicCard', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/services/topicCard')>(),
  fetchTopicCard: vi.fn(),
  adoptTopicCardDraft: vi.fn(),
  setTopicCardStage: vi.fn(),
  skipTopicCardFocus: vi.fn(),
}));

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };
const state = (overrides: Partial<TopicCardState> = {}): TopicCardState => ({
  stage: 1, version: 0, card: empty, pending: null, history: [], ...overrides,
});

describe('useTopicCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({ isStreaming: false });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads the card for an enabled conversation only', async () => {
    vi.mocked(fetchTopicCard).mockResolvedValue(state({ stage: 2 }));

    const { result, rerender } = renderHook(({ enabled }) => useTopicCard('conv-1', enabled), { initialProps: { enabled: false } });
    expect(fetchTopicCard).not.toHaveBeenCalled();

    rerender({ enabled: true });
    await waitFor(() => expect(result.current.state?.stage).toBe(2));
  });

  it('reports why the card is missing without throwing', async () => {
    vi.mocked(fetchTopicCard).mockRejectedValue(new TopicCardError('not_synced'));
    const { result } = renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(result.current.failure).toBe('not_synced'));
    expect(result.current.state).toBeNull();
  });

  it('re-reads the card after an answer finishes streaming', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchTopicCard).mockResolvedValue(state());
    renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(fetchTopicCard).toHaveBeenCalledTimes(1));

    act(() => useChatStore.setState({ isStreaming: true }));
    act(() => useChatStore.setState({ isStreaming: false }));
    await act(async () => { await vi.advanceTimersByTimeAsync(TOPIC_CARD_REFRESH_DELAYS_MS[1]); });

    expect(fetchTopicCard).toHaveBeenCalledTimes(1 + TOPIC_CARD_REFRESH_DELAYS_MS.length);
  });

  it('adopts the draft for the version the learner saw', async () => {
    vi.mocked(fetchTopicCard).mockResolvedValue(state({ version: 3, stage: 3 }));
    vi.mocked(adoptTopicCardDraft).mockResolvedValue({ state: state({ version: 4, stage: 3 }), adopted: true });
    const { result } = renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(result.current.state?.version).toBe(3));

    let outcome = '';
    await act(async () => { outcome = await result.current.adopt(); });

    expect(adoptTopicCardDraft).toHaveBeenCalledWith('conv-1', 3);
    expect(outcome).toBe('adopted');
    expect(result.current.state).toMatchObject({ version: 4, stage: 3 });
  });

  it('keeps the card when adoption is stale or fails', async () => {
    vi.mocked(fetchTopicCard).mockResolvedValue(state({ version: 1, stage: 1 }));
    const { result } = renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(result.current.state?.version).toBe(1));

    vi.mocked(adoptTopicCardDraft).mockResolvedValueOnce({ state: state({ version: 2, stage: 1 }), adopted: false });
    let outcome = '';
    await act(async () => { outcome = await result.current.adopt(); });
    expect(outcome).toBe('stale');
    expect(result.current.state?.version).toBe(2);

    vi.mocked(adoptTopicCardDraft).mockRejectedValueOnce(new TopicCardError('unavailable'));
    await act(async () => { outcome = await result.current.adopt(); });
    expect(outcome).toBe('failed');
    expect(result.current.state?.version).toBe(2);
  });

  it('jumps to any stage the learner picks and keeps the card on failure', async () => {
    vi.mocked(fetchTopicCard).mockResolvedValue(state({ version: 2, stage: 1 }));
    vi.mocked(setTopicCardStage).mockResolvedValueOnce(state({ version: 2, stage: 4 }));
    const { result } = renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(result.current.state?.version).toBe(2));

    let moved = false;
    await act(async () => { moved = await result.current.goToStage(4); });
    expect(setTopicCardStage).toHaveBeenCalledWith('conv-1', 4);
    expect(moved).toBe(true);
    expect(result.current.state?.stage).toBe(4);

    vi.mocked(setTopicCardStage).mockRejectedValueOnce(new TopicCardError('unavailable'));
    await act(async () => { moved = await result.current.goToStage(2); });
    expect(moved).toBe(false);
    expect(result.current.state?.stage).toBe(4);
  });
  it('sets the focus gap aside and keeps the card when that fails', async () => {
    const focus = { id: 'mother_question', kind: 'mother_question' as const, term: '' };
    vi.mocked(fetchTopicCard).mockResolvedValue(state({ stage: 3, focus }));
    vi.mocked(skipTopicCardFocus).mockResolvedValueOnce(state({ stage: 3, focus: null, skipped_focus: [focus.id] }));
    const { result } = renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(result.current.state?.focus?.id).toBe(focus.id));

    let ok = false;
    await act(async () => { ok = await result.current.skipFocus(focus.id); });
    expect(ok).toBe(true);
    expect(skipTopicCardFocus).toHaveBeenCalledWith('conv-1', focus.id);
    expect(result.current.state?.focus).toBeNull();

    vi.mocked(skipTopicCardFocus).mockRejectedValueOnce(new TopicCardError('unavailable'));
    await act(async () => { ok = await result.current.skipFocus('candidates'); });
    expect(ok).toBe(false);
    expect(result.current.state?.skipped_focus).toEqual([focus.id]);
  });
});
