'use client';

/**
 * Load and confirm the Topic Finder card for one conversation.
 *
 * The backend refreshes the pending draft in the background after each answer,
 * so the card is re-read a few seconds after streaming ends. Failures leave the
 * last known card in place; chat never depends on the card.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useChatStore } from '@/store/chat';
import {
  TopicCardError,
  confirmTopicCardStage,
  fetchTopicCard,
  type TopicCardFailure,
  type TopicCardState,
} from '@/services/topicCard';

/** Background extraction usually lands within a few seconds of the answer. */
export const TOPIC_CARD_REFRESH_DELAYS_MS = [3_000, 9_000];

export type ConfirmOutcome = 'advanced' | 'stale' | 'failed';

export interface UseTopicCardResult {
  state: TopicCardState | null;
  failure: TopicCardFailure | null;
  isConfirming: boolean;
  confirm: () => Promise<ConfirmOutcome>;
  reload: () => void;
}

export function useTopicCard(conversationId: string | null, enabled: boolean): UseTopicCardResult {
  const [state, setState] = useState<TopicCardState | null>(null);
  const [failure, setFailure] = useState<TopicCardFailure | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const requestRef = useRef(0);
  const isStreaming = useChatStore((store) => store.isStreaming);
  const wasStreamingRef = useRef(isStreaming);

  const load = useCallback(() => {
    if (!enabled || !conversationId) return;
    const request = ++requestRef.current;
    void fetchTopicCard(conversationId)
      .then((next) => {
        if (request !== requestRef.current) return;
        setState(next);
        setFailure(null);
      })
      .catch((error: unknown) => {
        if (request !== requestRef.current) return;
        setFailure(error instanceof TopicCardError ? error.reason : 'unavailable');
      });
  }, [conversationId, enabled]);

  // Reset and load whenever the conversation changes.
  useEffect(() => {
    requestRef.current += 1;
    setState(null);
    setFailure(null);
    load();
  }, [load]);

  // Re-read after an answer finishes, once the background proposal has had time to land.
  useEffect(() => {
    const finished = wasStreamingRef.current && !isStreaming;
    wasStreamingRef.current = isStreaming;
    if (!finished || !enabled || !conversationId) return;
    const timers = TOPIC_CARD_REFRESH_DELAYS_MS.map((delay) => window.setTimeout(load, delay));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [conversationId, enabled, isStreaming, load]);

  const confirm = useCallback(async (): Promise<ConfirmOutcome> => {
    if (!conversationId || !state || isConfirming) return 'failed';
    setIsConfirming(true);
    try {
      const result = await confirmTopicCardStage(conversationId, state.version);
      requestRef.current += 1;
      setState(result.state);
      setFailure(null);
      return result.advanced ? 'advanced' : 'stale';
    } catch {
      // Keep the card as it was; the learner can retry.
      return 'failed';
    } finally {
      setIsConfirming(false);
    }
  }, [conversationId, isConfirming, state]);

  return { state, failure, isConfirming, confirm, reload: load };
}
