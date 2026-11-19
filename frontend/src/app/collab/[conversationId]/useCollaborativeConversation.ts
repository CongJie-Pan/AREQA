'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { SharedConversation, SharedMessage } from '@/components/SharedConversation';
import type { CitationSource } from '@/components/Citations';
import type { AnswerBlock } from '@/database/schema';
import { createChatStream, type ChatMessage } from '@/services/chat-stream';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { ChatStreamError } from '@/utils/error';
import { generateUUID } from '@/utils/id';
import { logger } from '@/utils/logger';

/** Other participants' messages show up within this interval (no realtime yet). */
export const COLLAB_POLL_INTERVAL_MS = 5000;

export interface CollaborativeConversation extends SharedConversation {
  viewerRole: 'owner' | 'editor';
  viewerUserId: string;
  ownerUserId: string;
  isCollaborative: boolean;
}

export type CollabStatus = 'loading' | 'ready' | 'no_access' | 'error';
export type CollabNotice = 'collabSendFailed' | 'collabReplySaveFailed' | 'collabRateLimited' | null;

interface AppendPayload {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: string[];
  sources?: CitationSource[];
  answerBlocks?: AnswerBlock[];
  suggestions?: string[];
}

async function appendMessage(conversationId: string, message: AppendPayload): Promise<number> {
  const response = await authenticatedFetch(`/api/collab/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(message),
  }).catch(() => null);
  return response?.status ?? 0;
}

/**
 * Load, poll and send in a collaborative conversation.
 *
 * Each turn stores the asker's message first, then streams the reply through
 * the normal chat endpoint (which rebuilds the history server-side for
 * collaborative conversations), then stores the reply so everyone sees it.
 */
export function useCollaborativeConversation(conversationId: string, enabled: boolean) {
  const [status, setStatus] = useState<CollabStatus>('loading');
  const [conversation, setConversation] = useState<CollaborativeConversation | null>(null);
  const [draft, setDraft] = useState<SharedMessage | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [notice, setNotice] = useState<CollabNotice>(null);
  const sendingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async (): Promise<CollaborativeConversation | null> => {
    const response = await authenticatedFetch(`/api/collab/conversations/${conversationId}`).catch(() => null);
    if (!response) {
      setStatus((current) => (current === 'ready' ? current : 'error'));
      return null;
    }
    if (response.status === 401 || response.status === 403 || response.status === 404) {
      logger.info('collab_view_no_access', { component: 'CollabView', conversationId, status: response.status });
      setStatus('no_access');
      return null;
    }
    if (!response.ok) {
      // Keep showing the last good copy during transient failures.
      setStatus((current) => (current === 'ready' ? current : 'error'));
      return null;
    }
    const data = await response.json() as CollaborativeConversation;
    setConversation(data);
    setStatus('ready');
    return data;
  }, [conversationId]);

  useEffect(() => {
    if (!enabled) return undefined;
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !sendingRef.current) void load();
    }, COLLAB_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [enabled, load]);

  useEffect(() => () => abortRef.current?.abort(), []);

  /** Resolves false only when the question itself was not stored. */
  const send = useCallback(async (text: string): Promise<boolean> => {
    const content = text.trim();
    if (!content || !conversation || sendingRef.current) return false;
    sendingRef.current = true;
    setIsSending(true);
    setNotice(null);

    try {
      const userMessage: SharedMessage = {
        id: generateUUID(),
        role: 'user',
        content,
        authorUserId: conversation.viewerUserId,
        createdAt: new Date().toISOString(),
      };
      const userStatus = await appendMessage(conversationId, { id: userMessage.id, role: 'user', content });
      if (userStatus === 403) {
        setStatus('no_access');
        return false;
      }
      if (userStatus < 200 || userStatus >= 300) {
        logger.warn('collab_user_message_failed', { component: 'CollabView', conversationId, status: userStatus });
        setNotice('collabSendFailed');
        return false;
      }

      const withUser = { ...conversation, messages: [...conversation.messages, userMessage] };
      setConversation(withUser);

      const history: ChatMessage[] = withUser.messages
        .filter((message) => message.role === 'user' || message.role === 'assistant')
        .map((message) => ({ role: message.role, content: message.content, message_id: message.id }));

      const assistantId = generateUUID();
      let answer = '';
      let citations: string[] = [];
      let sources: CitationSource[] = [];
      let answerBlocks: AnswerBlock[] = [];
      let suggestions: string[] = [];
      let streamError: Error | null = null;
      const showDraft = () => setDraft({
        id: assistantId, role: 'assistant', content: answer, createdAt: new Date().toISOString(),
      });

      const controller = new AbortController();
      abortRef.current = controller;
      await createChatStream(history, {
        onThinkingStart: () => {},
        onThinkingContent: () => {},
        onThinkingEnd: () => {},
        onContent: (delta) => { answer += delta; showDraft(); },
        onCitations: (value) => { citations = value; },
        onSources: (value) => { sources = value; },
        onAnswerBlocks: (value) => { answerBlocks = value; },
        onSuggestions: (value) => { suggestions = value; },
        onDone: (value) => { if (value?.length) suggestions = value; },
        onError: (error) => { streamError = error; },
      }, controller.signal, false, false, 'auto', conversationId);
      abortRef.current = null;

      if (streamError) {
        const statusCode = (streamError as unknown) instanceof ChatStreamError
          ? (streamError as ChatStreamError).statusCode
          : 0;
        logger.warn('collab_stream_failed', { component: 'CollabView', conversationId, status: statusCode });
        setNotice(statusCode === 429 ? 'collabRateLimited' : 'collabSendFailed');
      }

      if (answer.trim()) {
        const replyStatus = await appendMessage(conversationId, {
          id: assistantId,
          role: 'assistant',
          content: answer,
          ...(citations.length ? { citations } : {}),
          ...(sources.length ? { sources } : {}),
          ...(answerBlocks.length ? { answerBlocks } : {}),
          ...(suggestions.length ? { suggestions } : {}),
        });
        if (replyStatus < 200 || replyStatus >= 300) {
          logger.warn('collab_reply_save_failed', { component: 'CollabView', conversationId, status: replyStatus });
          setNotice('collabReplySaveFailed');
        } else {
          logger.info('collab_turn_completed', { component: 'CollabView', conversationId });
        }
      }
      await load();
      return true;
    } finally {
      setDraft(null);
      sendingRef.current = false;
      setIsSending(false);
    }
  }, [conversation, conversationId, load]);

  const leave = useCallback(async () => {
    if (!conversation) return false;
    const response = await authenticatedFetch(
      `/api/collab/conversations/${conversationId}/members?userId=${encodeURIComponent(conversation.viewerUserId)}`,
      { method: 'DELETE' },
    ).catch(() => null);
    return Boolean(response?.ok);
  }, [conversation, conversationId]);

  return { status, conversation, draft, isSending, notice, send, refresh: load, leave };
}
