import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TOPIC_CARD_REFRESH_DELAYS_MS, useTopicCard } from '@/hooks/useTopicCard';
import { useChatStore } from '@/store/chat';
import { TopicCardError, confirmTopicCardStage, fetchTopicCard, type TopicCardState } from '@/services/topicCard';

vi.mock('@/services/topicCard', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/services/topicCard')>(),
  fetchTopicCard: vi.fn(),
  confirmTopicCardStage: vi.fn(),
}));

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };
const state = (overrides: Partial<TopicCardState> = {}): TopicCardState => ({
  stage: 0, version: 0, card: empty, pending: null, history: [], ...overrides,
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

  it('confirms the version the learner saw and adopts the returned state', async () => {
    vi.mocked(fetchTopicCard).mockResolvedValue(state({ version: 3, stage: 3 }));
    vi.mocked(confirmTopicCardStage).mockResolvedValue({ state: state({ version: 4, stage: 4 }), advanced: true });
    const { result } = renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(result.current.state?.version).toBe(3));

    let outcome = '';
    await act(async () => { outcome = await result.current.confirm(); });

    expect(confirmTopicCardStage).toHaveBeenCalledWith('conv-1', 3);
    expect(outcome).toBe('advanced');
    expect(result.current.state?.stage).toBe(4);
  });

  it('keeps the card when confirmation is stale or fails', async () => {
    vi.mocked(fetchTopicCard).mockResolvedValue(state({ version: 1, stage: 1 }));
    const { result } = renderHook(() => useTopicCard('conv-1', true));
    await waitFor(() => expect(result.current.state?.version).toBe(1));

    vi.mocked(confirmTopicCardStage).mockResolvedValueOnce({ state: state({ version: 2, stage: 2 }), advanced: false });
    let outcome = '';
    await act(async () => { outcome = await result.current.confirm(); });
    expect(outcome).toBe('stale');
    expect(result.current.state?.version).toBe(2);

    vi.mocked(confirmTopicCardStage).mockRejectedValueOnce(new TopicCardError('unavailable'));
    await act(async () => { outcome = await result.current.confirm(); });
    expect(outcome).toBe('failed');
    expect(result.current.state?.version).toBe(2);
  });
});
