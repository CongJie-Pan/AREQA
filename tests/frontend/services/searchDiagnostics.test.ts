import { beforeEach, describe, expect, it, vi } from 'vitest';
import { logSearchDiagnostic } from '@/services/searchDiagnostics';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { useFeatureStore } from '@/store/features';

vi.mock('@/services/authenticatedFetch', () => ({ authenticatedFetch: vi.fn() }));
vi.mock('@/store/features', () => ({ useFeatureStore: { getState: vi.fn() } }));
vi.mock('@/utils/logger', () => ({ logger: { info: vi.fn(), warn: vi.fn() } }));

describe('search diagnostics bridge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useFeatureStore.getState).mockReturnValue({ conversationHistoryDebugLogs: true } as ReturnType<typeof useFeatureStore.getState>);
    vi.mocked(authenticatedFetch).mockResolvedValue(new Response('{}', { status: 200 }));
  });

  it('forwards only state and correlation fields, never source/message bodies', async () => {
    logSearchDiagnostic('stream_request', {
      component: 'chatStream', conversationId: 'chat-1', requestId: 'request-1',
      searchMode: 'always', uiSearchMode: 'never', useWebSearch: true, useRag: false,
      sourceCount: 12, messageContent: 'PRIVATE MESSAGE', token: 'PRIVATE TOKEN',
    } as Parameters<typeof logSearchDiagnostic>[1]);
    const options = vi.mocked(authenticatedFetch).mock.calls[0][1]!;
    const body = JSON.parse(String(options.body));
    expect(body.event).toBe('chat_history_search_stream_request');
    expect(body.context).toMatchObject({ requestId: 'request-1', searchMode: 'always', uiSearchMode: 'never', sourceCount: 12 });
    expect(String(options.body)).not.toContain('PRIVATE');
    expect(options.signal).toBeInstanceOf(AbortSignal);
    await vi.waitFor(() => expect(vi.mocked(authenticatedFetch)).toHaveBeenCalledOnce());
  });

  it('does not transmit when runtime diagnostics are disabled', () => {
    vi.mocked(useFeatureStore.getState).mockReturnValue({ conversationHistoryDebugLogs: false } as ReturnType<typeof useFeatureStore.getState>);
    logSearchDiagnostic('toggle', { component: 'ChatInput', conversationId: 'chat-1', searchMode: 'always' });
    expect(authenticatedFetch).not.toHaveBeenCalled();
  });

  it('does not propagate a diagnostic network failure', async () => {
    vi.mocked(authenticatedFetch).mockRejectedValue(new Error('PRIVATE ERROR'));
    expect(() => logSearchDiagnostic('toggle', { component: 'ChatInput', conversationId: 'chat-1' })).not.toThrow();
    const { logger } = await import('@/utils/logger');
    await vi.waitFor(() => expect(logger.warn).toHaveBeenCalledWith('chat.search_diagnostic_failed',
      expect.objectContaining({ reason: 'delivery_failed' })));
    expect(JSON.stringify(vi.mocked(logger.warn).mock.calls)).not.toContain('PRIVATE');
  });
});

it('aborts a slow diagnostic without affecting chat code', async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(useFeatureStore.getState).mockReturnValue({ conversationHistoryDebugLogs: true } as ReturnType<typeof useFeatureStore.getState>);
    vi.mocked(authenticatedFetch).mockImplementation((_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));
    logSearchDiagnostic('toggle', { component: 'ChatInput', conversationId: 'chat-1' });
    const options = vi.mocked(authenticatedFetch).mock.lastCall?.[1];
    await vi.advanceTimersByTimeAsync(3000);
    expect(options?.signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  } finally {
    vi.useRealTimers();
  }
});
