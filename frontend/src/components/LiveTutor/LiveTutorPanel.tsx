'use client';

/**
 * AREQA Live Tutor voice panel.
 *
 * The panel owns the browser-only Realtime session and mirrors finalized voice
 * transcripts into the existing chat conversation. It is rendered inline by
 * ChatContainer between the message list and the normal text input so voice
 * mode does not replace the established composer.
 */

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { Mic, MicOff, RotateCcw, X } from 'lucide-react';
import Image from 'next/image';
import { Tooltip } from 'antd';
import { useStyles } from './styles';
import {
  RealtimeClientError,
  startRealtimeClient,
  type RealtimeClientController,
  type RealtimeStatus,
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

const STATUS_LABELS = {
  'zh-TW': {
    idle: '尚未連線',
    connecting: '正在連線',
    connected: '已連線',
    listening: '正在聆聽',
    thinking: '正在思考',
    speaking: '正在回應',
    muted: '麥克風已靜音',
    error: '連線發生問題',
  },
  'zh-CN': {
    idle: '尚未连接',
    connecting: '正在连接',
    connected: '已连接',
    listening: '正在聆听',
    thinking: '正在思考',
    speaking: '正在回应',
    muted: '麦克风已静音',
    error: '连接发生问题',
  },
  en: {
    idle: 'Not connected',
    connecting: 'Connecting',
    connected: 'Connected',
    listening: 'Listening',
    thinking: 'Thinking',
    speaking: 'Speaking',
    muted: 'Microphone muted',
    error: 'Connection issue',
  },
} as const;

const COPY = {
  'zh-TW': {
    title: 'AREQA 即時語音',
    mute: '靜音',
    unmute: '取消靜音',
    end: '結束語音',
    retry: '重新連線',
    permissionDenied: '麥克風權限已被封鎖，請在瀏覽器網站設定中允許後重試。',
    insecureContext: '麥克風只能在 HTTPS 安全連線中使用。',
    microphoneUnavailable: '找不到可用的麥克風。',
    microphoneBusy: '麥克風目前無法使用，請關閉其他錄音程式後重試。',
    setupFailed: '無法啟動即時語音，請確認麥克風權限、OpenAI Realtime 權限或稍後再試。',
  },
  'zh-CN': {
    title: 'AREQA 即时语音',
    mute: '静音',
    unmute: '取消静音',
    end: '结束语音',
    retry: '重新连接',
    permissionDenied: '麦克风权限已被阻止，请在浏览器网站设置中允许后重试。',
    insecureContext: '麦克风只能在 HTTPS 安全连接中使用。',
    microphoneUnavailable: '找不到可用的麦克风。',
    microphoneBusy: '麦克风目前无法使用，请关闭其他录音程序后重试。',
    setupFailed: '无法启动即时语音，请确认麦克风权限、OpenAI Realtime 权限或稍后再试。',
  },
  en: {
    title: 'AREQA Live Voice',
    mute: 'Mute',
    unmute: 'Unmute',
    end: 'End voice',
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
  const statusLabels = STATUS_LABELS[language];
  const panelRef = useRef<HTMLElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const controllerRef = useRef<RealtimeClientController | null>(null);
  const conversationIdRef = useRef('');
  const assistantMessageIdRef = useRef<string | null>(null);
  const assistantTranscriptRef = useRef('');
  const hasStartedRef = useRef(false);
  const isCancelledRef = useRef(false);

  const isOpen = useLiveTutorStore((state) => state.isOpen);
  const status = useLiveTutorStore((state) => state.status);
  const isMuted = useLiveTutorStore((state) => state.isMuted);
  const error = useLiveTutorStore((state) => state.error);
  const close = useLiveTutorStore((state) => state.close);
  const setStatus = useLiveTutorStore((state) => state.setStatus);
  const setMuted = useLiveTutorStore((state) => state.setMuted);
  const setError = useLiveTutorStore((state) => state.setError);
  const resetTranscript = useLiveTutorStore((state) => state.resetTranscript);

  const addUserMessage = useChatStore((state) => state.addUserMessage);
  const addAssistantMessage = useChatStore((state) => state.addAssistantMessage);
  const updateAssistantMessage = useChatStore((state) => state.updateAssistantMessage);
  const createConversation = useConversationStore((state) => state.createConversation);
  const selectConversation = useConversationStore((state) => state.selectConversation);

  const ensureConversationId = useCallback(async (): Promise<string> => {
    const chatMessages = useChatStore.getState().messages;
    const selectedConversationId = selectLiveTutorConversationId(
      useConversationStore.getState().activeConversationId,
      chatMessages,
    );
    if (selectedConversationId) {
      conversationIdRef.current = selectedConversationId;
      return selectedConversationId;
    }
    if (canPersistHistory()) {
      const createdId = await createConversation();
      conversationIdRef.current = createdId;
      return createdId;
    }
    const guestConversationId = generateUUID();
    selectConversation(guestConversationId);
    conversationIdRef.current = guestConversationId;
    return guestConversationId;
  }, [createConversation, selectConversation]);

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
    conversationId: string,
  ) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    const userMessageId = addUserMessage(trimmed, conversationId);
    bumpConversationPreview(conversationId, trimmed);
    if (canPersistHistory()) {
      await databaseService.message.add(conversationId, {
        id: userMessageId,
        role: 'user',
        content: trimmed,
      });
    }
  }, [addUserMessage, bumpConversationPreview]);

  const finalizeAssistantDraft = useCallback((
    conversationId: string,
    contentOverride?: string,
  ) => {
    const content = (contentOverride ?? assistantTranscriptRef.current).trim();
    const assistantMessageId = assistantMessageIdRef.current;
    if (!assistantMessageId || !content) {
      assistantMessageIdRef.current = null;
      assistantTranscriptRef.current = '';
      return;
    }

    updateAssistantMessage(assistantMessageId, {
      content,
      isStreaming: false,
    });
    assistantMessageIdRef.current = null;
    assistantTranscriptRef.current = '';
    bumpConversationPreview(conversationId, content);
    if (canPersistHistory()) {
      void databaseService.message.add(conversationId, {
        id: assistantMessageId,
        role: 'assistant',
        content,
      }).catch(() => undefined);
    }
  }, [bumpConversationPreview, updateAssistantMessage]);

  const start = useCallback(async () => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    isCancelledRef.current = false;
    conversationIdRef.current = '';
    resetTranscript();
    setError(null);
    const conversationId = await ensureConversationId();
    logger.info('realtime.voice_session_bound', {
      component: 'LiveTutorPanel',
      conversationId,
      contextMessageCount: selectLiveTutorMessages(useChatStore.getState().messages, conversationId).length,
    });
    const controller = await startRealtimeClient({
      conversationId,
      interfaceLanguage: language,
      recentMessages: () => selectLiveTutorMessages(useChatStore.getState().messages, conversationId),
      onRemoteStream: (stream) => {
        if (isCancelledRef.current) return;
        if (audioRef.current) {
          audioRef.current.srcObject = stream;
          void audioRef.current.play();
        }
      },
      onInputAudioLevel: (level) => {
        if (isCancelledRef.current) return;
        const scale = 1 + Math.min(Math.max(level, 0), 1) * 0.18;
        panelRef.current?.style.setProperty('--live-tutor-audio-scale', scale.toFixed(3));
        panelRef.current?.style.setProperty('--live-tutor-audio-level', level.toFixed(3));
      },
      onStatus: (nextStatus: RealtimeStatus) => {
        if (!isCancelledRef.current) setStatus(nextStatus);
      },
      onAssistantResponseStarted: () => {
        if (isCancelledRef.current) return;
        finalizeAssistantDraft(conversationId);
      },
      onUserTranscript: (transcript) => {
        if (isCancelledRef.current) return;
        finalizeAssistantDraft(conversationId);
        void persistUserTranscript(transcript, conversationId);
      },
      onAssistantTranscriptDelta: (delta) => {
        if (isCancelledRef.current) return;
        if (!assistantMessageIdRef.current) {
          assistantMessageIdRef.current = addAssistantMessage(conversationId);
        }
        assistantTranscriptRef.current += delta;
        updateAssistantMessage(assistantMessageIdRef.current, {
          content: assistantTranscriptRef.current,
          isStreaming: true,
        });
      },
      onAssistantTranscriptDone: (transcript) => {
        if (isCancelledRef.current) return;
        finalizeAssistantDraft(conversationId, transcript);
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
  }, [
    addAssistantMessage,
    ensureConversationId,
    finalizeAssistantDraft,
    labels.insecureContext,
    labels.microphoneBusy,
    labels.microphoneUnavailable,
    labels.permissionDenied,
    labels.setupFailed,
    language,
    persistUserTranscript,
    resetTranscript,
    setError,
    setStatus,
    updateAssistantMessage,
  ]);

  const stop = useCallback(() => {
    isCancelledRef.current = true;
    finalizeAssistantDraft(conversationIdRef.current);
    controllerRef.current?.disconnect();
    controllerRef.current = null;
    hasStartedRef.current = false;
    assistantMessageIdRef.current = null;
    assistantTranscriptRef.current = '';
    conversationIdRef.current = '';
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
    panelRef.current?.style.setProperty('--live-tutor-audio-level', '0');
    setStatus('idle');
  }, [finalizeAssistantDraft, setStatus]);

  const handleClose = useCallback(() => {
    stop();
    close();
  }, [close, stop]);

  const handleRetry = useCallback(() => {
    stop();
    void start();
  }, [start, stop]);

  const handleMute = useCallback(() => {
    const nextMuted = !isMuted;
    controllerRef.current?.setMuted(nextMuted);
    setMuted(nextMuted);
  }, [isMuted, setMuted]);

  useEffect(() => {
    if (!isOpen) return;
    void start();
    return () => {
      stop();
    };
  }, [isOpen, start, stop]);

  useEffect(() => {
    const sessionConversationId = conversationIdRef.current;
    if (!isOpen || !sessionConversationId || activeConversationId === sessionConversationId) return;
    logger.info('realtime.voice_session_closed_on_conversation_change', {
      component: 'LiveTutorPanel',
      conversationId: sessionConversationId,
    });
    handleClose();
  }, [activeConversationId, handleClose, isOpen]);

  const isActiveAudio = useMemo(() => (
    status === 'listening' || status === 'thinking' || status === 'speaking'
  ), [status]);

  if (!isOpen) return null;

  return (
    <section
      ref={panelRef}
      className={cx(styles.panel, hasMessages && styles.panelWithMessages)}
      aria-label={labels.title}
    >
      <div className={styles.header}>
        <div className={styles.status}>{statusLabels[status]}</div>
        <div className={styles.controlCluster}>
          <Tooltip title={isMuted ? labels.unmute : labels.mute} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button type="button" className={styles.muteButton} onClick={handleMute} aria-label={isMuted ? labels.unmute : labels.mute}>
              {isMuted ? <MicOff size={20} /> : <Mic size={20} />}
            </button>
          </Tooltip>
          <Tooltip title={labels.end} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button type="button" className={styles.closeButton} onClick={handleClose} aria-label={labels.end}>
              <X size={22} strokeWidth={1.8} />
            </button>
          </Tooltip>
        </div>
      </div>

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
          <div className={cx(styles.logoOrb, isActiveAudio && styles.logoOrbActive)}>
            <Image
              src="/icon/areqa_icon_v4_circle.png"
              alt=""
              width={192}
              height={192}
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
