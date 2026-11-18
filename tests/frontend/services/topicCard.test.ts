import { beforeEach, describe, expect, it, vi } from 'vitest';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { TopicCardError, adoptTopicCardDraft, fetchTopicCard, setTopicCardStage, visibleCard } from '@/services/topicCard';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

const empty = { pain_point: '', mother_question: '', candidates: [], operationalization: [], discarded: [], objections: [] };

describe('topic card service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reads the card through the proxy', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({ stage: 1, version: 1, card: empty, pending: null, history: [] })));
    const state = await fetchTopicCard('conv/1');
    expect(state.stage).toBe(1);
    expect(vi.mocked(authenticatedFetch).mock.calls[0][0]).toBe('/api/research-coach/conv%2F1/card');
  });

  it('maps a missing conversation to not_synced and other errors to unavailable', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('{}', { status: 404 }));
    await expect(fetchTopicCard('c')).rejects.toMatchObject({ reason: 'not_synced' });
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('{}', { status: 503 }));
    await expect(adoptTopicCardDraft('c', 0)).rejects.toBeInstanceOf(TopicCardError);
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('{}', { status: 503 }));
    await expect(setTopicCardStage('c', 2)).rejects.toMatchObject({ reason: 'unavailable' });
  });

  it('adopts with the seen version', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({ adopted: true, state: { stage: 2, version: 2, card: empty, pending: null, history: [] } })));
    const result = await adoptTopicCardDraft('c', 1);
    expect(result.adopted).toBe(true);
    const [url, init] = vi.mocked(authenticatedFetch).mock.calls[0];
    expect(url).toBe('/api/research-coach/c/confirm');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ version: 1 });
  });

  it('sets the stage the learner picked', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({ stage: 4, version: 2, card: empty, pending: null, history: [] })));
    const state = await setTopicCardStage('c', 4);
    expect(state.stage).toBe(4);
    const [url, init] = vi.mocked(authenticatedFetch).mock.calls[0];
    expect(url).toBe('/api/research-coach/c/stage');
    expect(JSON.parse(String(init?.body))).toEqual({ stage: 4 });
  });

  it('shows the pending draft when one exists', () => {
    const draft = { ...empty, pain_point: 'draft' };
    expect(visibleCard({ stage: 0, version: 0, card: empty, pending: { card: draft, notes: [] }, history: [] }).pain_point).toBe('draft');
    expect(visibleCard({ stage: 0, version: 0, card: empty, pending: null, history: [] })).toBe(empty);
  });
});
