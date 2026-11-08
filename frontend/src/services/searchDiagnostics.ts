/** Metadata-only search diagnostics, using the existing opt-in backend debug channel. */
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { useFeatureStore } from '@/store/features';
import { logger } from '@/utils/logger';
import type { SearchMode } from '@/store/chat/types';

type SearchDiagnosticEvent = 'toggle' | 'send_clicked' | 'stream_request' | 'sources_received';
interface SearchDiagnosticContext {
  component: 'ChatInput' | 'chatStream';
  conversationId: string;
  requestId?: string;
  previousSearchMode?: SearchMode;
  searchMode?: SearchMode;
  useWebSearch?: boolean;
  uiSearchMode?: SearchMode;
  uiUseWebSearch?: boolean;
  useRag?: boolean;
  attachmentCount?: number;
  sourceCount?: number;
}

/**
 * Forward allowlisted settings/counts without delaying the chat request.
 *
 * Args:
 *   event: Known search lifecycle event.
 *   context: State only; message text, URLs and credentials are never selected.
 *
 * Side effects:
 *   With conversationHistoryDebugLogs enabled, posts chat_history_search_* events
 *   to the existing backend logger. Delivery is best-effort with a three-second
 *   timeout; failure logs a fixed reason and never interrupts sending a message.
 */
export function logSearchDiagnostic(event: SearchDiagnosticEvent, context: SearchDiagnosticContext): void {
  if (!useFeatureStore.getState().conversationHistoryDebugLogs) return;
  const allowed = ['component', 'conversationId', 'requestId', 'previousSearchMode', 'searchMode',
    'useWebSearch', 'uiSearchMode', 'uiUseWebSearch', 'useRag', 'attachmentCount', 'sourceCount'] as const;
  const safe: Record<string, string | number | boolean> = { clientTimestampMs: Date.now() };
  for (const key of allowed) {
    const value = context[key];
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') safe[key] = value;
  }
  const eventName = `chat_history_search_${event}`;
  logger.info(eventName, safe);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3000);
  void authenticatedFetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'}/api/v1/conversation-history/debug-log`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: eventName, context: safe }), signal: controller.signal,
  }).then((response) => {
    if (!response.ok) logger.warn('chat.search_diagnostic_failed', { eventName, status: response.status });
  }).catch(() => {
    logger.warn('chat.search_diagnostic_failed', { eventName, reason: 'delivery_failed' });
  }).finally(() => clearTimeout(timer));
}
