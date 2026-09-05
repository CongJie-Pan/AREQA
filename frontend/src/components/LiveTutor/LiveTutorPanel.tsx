'use client';

/**
 * AREQA Live Tutor voice panel.
 *
 * The panel owns the browser-only Realtime session and mirrors finalized voice
 * transcripts into the existing chat conversation. It is rendered inline by
 * ChatContainer between the message list and the normal text input. The
 * established composer swaps its trailing controls while voice mode is active.
 */

import React, { useCallback, useEffect, useRef } from 'react';
import { RotateCcw } from 'lucide-react';
import Image from 'next/image';
import { Tooltip } from 'antd';
import { useStyles } from './styles';
import {
  RealtimeClientError,
  startRealtimeClient,
  type RealtimeClientController,
} from '@/services/realtime';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useLiveTutorStore } from '@/store/liveTutor';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import { generateUUID } from '@/utils/id';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';
import { selectLiveTutorConversationId, selectLiveTutorMessages } from './session';
import { normalizeVoiceTranscript } from '@/services/realtime/language';

const COPY = {
  'zh-TW': {
    title: 'AREQA 即時語音',
    retry: '重新連線',
    permissionDenied: '麥克風權限已被封鎖，請在瀏覽器網站設定中允許後重試。',
    insecureContext: '麥克風只能在 HTTPS 安全連線中使用。',
    microphoneUnavailable: '找不到可用的麥克風。',
    microphoneBusy: '麥克風目前無法使用，請關閉其他錄音程式後重試。',
    setupFailed: '無法啟動即時語音，請確認麥克風權限、OpenAI Realtime 權限或稍後再試。',
  },
  'zh-CN': {
    title: 'AREQA 即时语音',
    retry: '重新连接',
    permissionDenied: '麦克风权限已被阻止，请在浏览器网站设置中允许后重试。',
    insecureContext: '麦克风只能在 HTTPS 安全连接中使用。',
    microphoneUnavailable: '找不到可用的麦克风。',
    microphoneBusy: '麦克风目前无法使用，请关闭其他录音程序后重试。',
    setupFailed: '无法启动即时语音，请确认麦克风权限、OpenAI Realtime 权限或稍后再试。',
  },
  en: {
    title: 'AREQA Live Voice',
    retry: 'Reconnect',
    permissionDenied: 'Microphone access is blocked. Allow it in browser site settings, then retry.',
    insecureContext: 'Microphone access requires a secure HTTPS connection.',
    microphoneUnavailable: 'No microphone is available.',
    microphoneBusy: 'The microphone is unavailable. Close other recording apps and retry.',
    setupFailed: 'Unable to start live voice. Check microphone permission, OpenAI Realtime access, or try again later.',
  },
} as const;

function canPersistHistory(): boolean {
  return getCurrentUserId() !== null;
}

function conversationPreview(content: string): string {
  return content.slice(0, 100);
}

export interface LiveTutorPanelProps {
  activeConversationId?: string | null;
  hasMessages?: boolean;
}

/**
 * Renders and owns one conversation-bound browser Realtime voice session.
 *
 * Final transcripts are written to the normal chat store; the panel deliberately
 * renders no duplicate transcript surface. Safe lifecycle logs contain ids and
 * counts only, never speech or model output.
 *
 * @param props - Active conversation and whether normal messages are visible.
 * @returns The inline voice panel, or `null` while voice mode is closed.
 */
export function LiveTutorPanel({ activeConversationId, hasMessages = false }: LiveTutorPanelProps) {
  const { styles, cx } = useStyles();
  const { language } = useUserPreferences();
  const labels = COPY[language];
  const panelRef = useRef<HTMLElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const controllerRef = useRef<RealtimeClientController | null>(null);
  const conversationIdRef = useRef('');
  const persistedConversationIdRef = useRef('');
  const conversationMaterializationRef = useRef<Promise<string> | null>(null);
  const transcriptQueueRef = useRef<Promise<void>>(Promise.resolve());
  const assistantMessageIdRef = useRef<string | null>(null);
  const assistantTranscriptRef = useRef('');
  const lastVoiceMessageIdRef = useRef<string | null>(null);
  const playbackRef = useRef<'waiting' | 'playing' | 'finished' | 'interrupted'>('waiting');
  const inputLevelRef = useRef(0);
  const outputLevelRef = useRef(0);
  const userTurnIdsRef = useRef(new Map<string, string>());
  const hasStartedRef = useRef(false);
  const isCancelledRef = useRef(false);

  const isOpen = useLiveTutorStore((state) => state.isOpen);
  const isMuted = useLiveTutorStore((state) => state.isMuted);
  const error = useLiveTutorStore((state) => state.error);
  const close = useLiveTutorStore((state) => state.close);
  const setStatus = useLiveTutorStore((state) => state.setStatus);
  const setError = useLiveTutorStore((state) => state.setError);
  const resetTranscript = useLiveTutorStore((state) => state.resetTranscript);

  const addUserMessage = useChatStore((state) => state.addUserMessage);
  const addAssistantMessage = useChatStore((state) => state.addAssistantMessage);
  const updateAssistantMessage = useChatStore((state) => state.updateAssistantMessage);
  const createConversation = useConversationStore((state) => state.createConversation);
  const selectConversation = useConversationStore((state) => state.selectConversation);

  const prepareSessionConversationId = useCallback((): string => {
    const chatMessages = useChatStore.getState().messages;
    const selectedConversationId = selectLiveTutorConversationId(
      useConversationStore.getState().activeConversationId,
      chatMessages,
    );
    if (selectedConversationId) {
      conversationIdRef.current = selectedConversationId;
      persistedConversationIdRef.current = selectedConversationId;
      return selectedConversationId;
    }

    // Realtime only needs a correlation id while the session is empty. Keeping
    // it ephemeral prevents opening voice mode from creating an empty chat.
    const ephemeralConversationId = generateUUID();
    conversationIdRef.current = ephemeralConversationId;
    persistedConversationIdRef.current = '';
    return ephemeralConversationId;
  }, []);

  const ensurePersistedConversationId = useCallback(async (): Promise<string> => {
    if (persistedConversationIdRef.current) return persistedConversationIdRef.current;
    if (conversationMaterializationRef.current) return conversationMaterializationRef.current;

    const ephemeralConversationId = conversationIdRef.current || generateUUID();
    conversationMaterializationRef.current = (async () => {
      const isAuthenticated = canPersistHistory();
      const persistedConversationId = isAuthenticated
        ? await createConversation()
        : ephemeralConversationId;
      if (!isAuthenticated) selectConversation(persistedConversationId);
      persistedConversationIdRef.current = persistedConversationId;
      conversationIdRef.current = persistedConversationId;
      logger.info('realtime.voice_conversation_materialized', {
        component: 'LiveTutorPanel',
        conversationId: persistedConversationId,
      });
      return persistedConversationId;
    })();

    try {
      return await conversationMaterializationRef.current;
    } finally {
      conversationMaterializationRef.current = null;
    }
  }, [createConversation, selectConversation]);

  const enqueueTranscriptWork = useCallback((work: () => Promise<void>): void => {
    transcriptQueueRef.current = transcriptQueueRef.current
      .then(work)
      .catch((queueError) => {
        logger.error(
          'realtime.transcript_persistence_failed',
          queueError instanceof Error ? queueError : new Error(String(queueError)),
          { component: 'LiveTutorPanel' },
        );
      });
  }, []);

  const updateAudioScale = useCallback(() => {
    const level = Math.max(inputLevelRef.current, outputLevelRef.current);
    const scale = 1 + Math.min(Math.max(level, 0), 1) * 0.18;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', scale.toFixed(3));
  }, []);

  const bumpConversationPreview = useCallback((conversationId: string, content: string) => {
    const conversationStore = useConversationStore.getState();
    const existing = conversationStore.conversations.find((conversation) => conversation.id === conversationId);
    if (!existing) return;
    conversationStore.updateConversation(conversationId, {
      lastMessagePreview: conversationPreview(content),
      updatedAt: new Date(),
      messageCount: existing.messageCount + 1,
    });
  }, []);

  const persistUserTranscript = useCallback(async (
    content: string,
    itemId?: string,
  ) => {
    const trimmed = normalizeVoiceTranscript(content, language).trim();
    if (!trimmed) return;
    const conversationId = await ensurePersistedConversationId();
    const pendingId = itemId ? userTurnIdsRef.current.get(itemId) : undefined;
    const userMessageId = pendingId ?? addUserMessage(trimmed, conversationId);
    if (pendingId) useChatStore.getState().updateMessageContent(pendingId, trimmed);
    if (itemId) userTurnIdsRef.current.delete(itemId);
    bumpConversationPreview(conversationId, trimmed);
    if (canPersistHistory()) {
      await databaseService.message.add(conversationId, {
        id: userMessageId,
        role: 'user',
        content: trimmed,
        createdAt: useChatStore.getState().messages.find((message) => message.id === userMessageId)?.createdAt,
      });
    }
  }, [addUserMessage, bumpConversationPreview, ensurePersistedConversationId, language]);

  const finalizeAssistantDraft = useCallback(async (
    contentOverride?: string,
  ): Promise<void> => {
    const content = normalizeVoiceTranscript(contentOverride ?? assistantTranscriptRef.current, language).trim();
    if (!content) {
      assistantMessageIdRef.current = null;
      assistantTranscriptRef.current = '';
      return;
    }

    const conversationId = await ensurePersistedConversationId();
    const assistantMessageId = assistantMessageIdRef.current
      ?? addAssistantMessage(conversationId);
    lastVoiceMessageIdRef.current = assistantMessageId;
    updateAssistantMessage(assistantMessageId, {
      content,
      isStreaming: false,
      voicePlayback: playbackRef.current === 'waiting' ? 'finished' : playbackRef.current,
    });
    assistantMessageIdRef.current = null;
    assistantTranscriptRef.current = '';
    bumpConversationPreview(conversationId, content);
    if (canPersistHistory()) {
      void databaseService.message.add(conversationId, {
        id: assistantMessageId,
        role: 'assistant',
        content,
        createdAt: useChatStore.getState().messages.find((message) => message.id === assistantMessageId)?.createdAt,
      }).catch(() => undefined);
    }
  }, [addAssistantMessage, bumpConversationPreview, ensurePersistedConversationId, updateAssistantMessage, language]);

  const appendAssistantTranscript = useCallback(async (delta: string): Promise<void> => {
    if (!delta) return;
    assistantTranscriptRef.current += delta;
    const conversationId = await ensurePersistedConversationId();
    if (!assistantMessageIdRef.current) {
      assistantMessageIdRef.current = addAssistantMessage(conversationId);
    }
    lastVoiceMessageIdRef.current = assistantMessageIdRef.current;
    updateAssistantMessage(assistantMessageIdRef.current, {
      content: normalizeVoiceTranscript(assistantTranscriptRef.current, language),
      isStreaming: true,
      voicePlayback: playbackRef.current,
    });
  }, [addAssistantMessage, ensurePersistedConversationId, updateAssistantMessage, language]);

  const start = useCallback(async () => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    isCancelledRef.current = false;
    conversationIdRef.current = '';
    persistedConversationIdRef.current = '';
    conversationMaterializationRef.current = null;
    transcriptQueueRef.current = Promise.resolve();
    resetTranscript();
    playbackRef.current = 'waiting';
    inputLevelRef.current = 0;
    outputLevelRef.current = 0;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
    userTurnIdsRef.current.clear();
    setError(null);
    const conversationId = prepareSessionConversationId();
    logger.info('realtime.voice_session_bound', {
      component: 'LiveTutorPanel',
      conversationId,
      contextMessageCount: selectLiveTutorMessages(useChatStore.getState().messages, conversationId).length,
      isPersistedConversation: persistedConversationIdRef.current === conversationId,
    });
    const controller = await startRealtimeClient({
      conversationId,
      getConversationId: () => persistedConversationIdRef.current || conversationId,
      interfaceLanguage: language,
      recentMessages: () => selectLiveTutorMessages(
        useChatStore.getState().messages,
        persistedConversationIdRef.current || conversationId,
      ),
      onRemoteStream: (stream) => {
        if (isCancelledRef.current) return;
        if (audioRef.current) {
          audioRef.current.srcObject = stream;
          void audioRef.current.play();
        }
      },
      onInputAudioLevel: (level) => {
        if (isCancelledRef.current) return;
        inputLevelRef.current = Math.min(Math.max(level, 0), 1);
        updateAudioScale();
      },
      onOutputAudioLevel: (level) => {
        if (isCancelledRef.current) return;
        outputLevelRef.current = Math.min(Math.max(level, 0), 1);
        updateAudioScale();
      },
      onStatus: (nextStatus) => {
        if (!isCancelledRef.current) setStatus(nextStatus);
      },
      onAssistantResponseStarted: () => {
        if (isCancelledRef.current) return;
        playbackRef.current = 'waiting';
        enqueueTranscriptWork(async () => {
          await finalizeAssistantDraft();
          lastVoiceMessageIdRef.current = null;
        });
      },
      onPlaybackState: (state) => {
        if (isCancelledRef.current) return;
        playbackRef.current = state === 'started' ? 'playing' : state === 'stopped' ? 'finished' : 'interrupted';
        const playback = playbackRef.current;
        enqueueTranscriptWork(async () => {
          if (lastVoiceMessageIdRef.current) {
            updateAssistantMessage(lastVoiceMessageIdRef.current, { voicePlayback: playback });
          }
        });
      },
      onUserTurnCommitted: (itemId) => {
        if (isCancelledRef.current) return;
        enqueueTranscriptWork(async () => {
          if (userTurnIdsRef.current.has(itemId)) return;
          const boundId = await ensurePersistedConversationId();
          userTurnIdsRef.current.set(itemId, addUserMessage('', boundId));
        });
      },
      onUserTranscript: (transcript, itemId) => {
        if (isCancelledRef.current) return;
        enqueueTranscriptWork(async () => {
          await persistUserTranscript(transcript, itemId);
        });
      },
      onAssistantTranscriptDelta: (delta) => {
        if (isCancelledRef.current) return;
        enqueueTranscriptWork(() => appendAssistantTranscript(delta));
      },
      onAssistantTranscriptDone: (transcript) => {
        if (isCancelledRef.current) return;
        enqueueTranscriptWork(() => finalizeAssistantDraft(transcript));
      },
      onError: (nextError) => {
        if (isCancelledRef.current) return;
        const localizedErrors = {
          microphone_denied: labels.permissionDenied,
          microphone_insecure_context: labels.insecureContext,
          microphone_unavailable: labels.microphoneUnavailable,
          microphone_busy: labels.microphoneBusy,
          provider_error: nextError.message,
        } as const;
        const message = nextError instanceof RealtimeClientError
          ? localizedErrors[nextError.code]
          : nextError.message || labels.setupFailed;
        setError(message);
      },
    });
    if (isCancelledRef.current || !useLiveTutorStore.getState().isOpen) {
      controller.disconnect();
      return;
    }
    controllerRef.current = controller;
    controller.setMuted(useLiveTutorStore.getState().isMuted);
  }, [
    appendAssistantTranscript,
    enqueueTranscriptWork,
    finalizeAssistantDraft,
    labels.insecureContext,
    labels.microphoneBusy,
    labels.microphoneUnavailable,
    labels.permissionDenied,
    labels.setupFailed,
    language,
    persistUserTranscript,
    prepareSessionConversationId,
    resetTranscript,
    setError,
    setStatus,
    updateAudioScale,
    updateAssistantMessage,
    addUserMessage,
    ensurePersistedConversationId,
  ]);

  const stop = useCallback(() => {
    isCancelledRef.current = true;
    controllerRef.current?.disconnect();
    controllerRef.current = null;
    hasStartedRef.current = false;
    enqueueTranscriptWork(async () => {
      await finalizeAssistantDraft();
      if (lastVoiceMessageIdRef.current) {
        updateAssistantMessage(lastVoiceMessageIdRef.current, { voicePlayback: 'finished', isStreaming: false });
      }
      for (const id of userTurnIdsRef.current.values()) {
        useChatStore.getState().removeMessage(id);
      }
      userTurnIdsRef.current.clear();
    });
    inputLevelRef.current = 0;
    outputLevelRef.current = 0;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
    setStatus('idle');
  }, [setStatus, enqueueTranscriptWork, finalizeAssistantDraft, updateAssistantMessage]);

  const handleClose = useCallback(() => {
    stop();
    close();
  }, [close, stop]);

  const handleRetry = useCallback(() => {
    stop();
    void start();
  }, [start, stop]);

  useEffect(() => {
    if (!isOpen) return;
    void start();
    return () => {
      stop();
    };
  }, [isOpen, start, stop]);

  useEffect(() => {
    controllerRef.current?.setMuted(isMuted);
  }, [isMuted]);

  useEffect(() => {
    const sessionConversationId = persistedConversationIdRef.current;
    if (!isOpen || !sessionConversationId || activeConversationId === sessionConversationId) return;
    logger.info('realtime.voice_session_closed_on_conversation_change', {
      component: 'LiveTutorPanel',
      conversationId: sessionConversationId,
    });
    handleClose();
  }, [activeConversationId, handleClose, isOpen]);

  if (!isOpen) return null;

  return (
    <section
      ref={panelRef}
      className={cx(styles.panel, hasMessages && styles.panelWithMessages)}
      aria-label={labels.title}
    >
      <div className={styles.body}>
        {error && (
          <div className={styles.errorRow}>
            <div className={styles.error}>{error}</div>
            <Tooltip title={labels.retry} color="#262626" styles={{ container: { color: '#ffffff' } }}>
              <button type="button" className={styles.retryButton} onClick={handleRetry} aria-label={labels.retry}>
                <RotateCcw size={17} />
              </button>
            </Tooltip>
          </div>
        )}

        <div className={styles.voiceCore} aria-hidden>
          <div className={styles.logoOrb}>
            <Image
              src="/icon/areqa_icon_v4_circle.png"
              alt=""
              width={192}
              height={192}
              unoptimized
              className={styles.logoImage}
              draggable={false}
              priority
            />
          </div>
        </div>
      </div>

      <audio ref={audioRef} autoPlay />
    </section>
  );
}

export default LiveTutorPanel;
