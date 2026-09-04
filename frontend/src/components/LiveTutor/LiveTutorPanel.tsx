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
import { Mic, MicOff, X } from 'lucide-react';
import Image from 'next/image';
import { Tooltip } from 'antd';
import { useStyles } from './styles';
import { startRealtimeClient, type RealtimeClientController, type RealtimeStatus } from '@/services/realtime';
import { useChatStore, type DisplayMessage } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useLiveTutorStore } from '@/store/liveTutor';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import { generateUUID } from '@/utils/id';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';

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
    you: '你說',
    areqa: 'AREQA 回應',
    emptyUser: '開始說話後，這裡會顯示辨識文字。',
    emptyAssistant: 'AREQA 的語音回覆字幕會顯示在這裡。',
    mute: '靜音',
    unmute: '取消靜音',
    end: '結束語音',
    permissionDenied: '請允許瀏覽器使用麥克風，才能開始即時語音。',
    setupFailed: '無法啟動即時語音，請確認麥克風權限、OpenAI Realtime 權限或稍後再試。',
  },
  'zh-CN': {
    title: 'AREQA 即时语音',
    you: '你说',
    areqa: 'AREQA 回应',
    emptyUser: '开始说话后，这里会显示识别文字。',
    emptyAssistant: 'AREQA 的语音回复字幕会显示在这里。',
    mute: '静音',
    unmute: '取消静音',
    end: '结束语音',
    permissionDenied: '请允许浏览器使用麦克风，才能开始即时语音。',
    setupFailed: '无法启动即时语音，请确认麦克风权限、OpenAI Realtime 权限或稍后再试。',
  },
  en: {
    title: 'AREQA Live Voice',
    you: 'You said',
    areqa: 'AREQA replied',
    emptyUser: 'Your recognized speech will appear here.',
    emptyAssistant: "AREQA's spoken reply captions will appear here.",
    mute: 'Mute',
    unmute: 'Unmute',
    end: 'End voice',
    permissionDenied: 'Allow microphone access in your browser to start live voice.',
    setupFailed: 'Unable to start live voice. Check microphone permission, OpenAI Realtime access, or try again later.',
  },
} as const;

function canPersistHistory(): boolean {
  return getCurrentUserId() !== null;
}

function conversationPreview(content: string): string {
  return content.slice(0, 100);
}

function isMicrophonePermissionError(error: Error): boolean {
  return error.name === 'NotAllowedError'
    || error.name === 'SecurityError'
    || error.message.toLowerCase().includes('permission');
}

export interface LiveTutorPanelProps {
  activeConversationId?: string | null;
}

export function LiveTutorPanel({ activeConversationId }: LiveTutorPanelProps) {
  const { styles, cx } = useStyles();
  const { language } = useUserPreferences();
  const labels = COPY[language];
  const statusLabels = STATUS_LABELS[language];
  const panelRef = useRef<HTMLElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const controllerRef = useRef<RealtimeClientController | null>(null);
  const conversationIdRef = useRef<string>(activeConversationId || '');
  const assistantMessageIdRef = useRef<string | null>(null);
  const assistantTranscriptRef = useRef('');
  const hasStartedRef = useRef(false);
  const isCancelledRef = useRef(false);

  const isOpen = useLiveTutorStore((state) => state.isOpen);
  const status = useLiveTutorStore((state) => state.status);
  const isMuted = useLiveTutorStore((state) => state.isMuted);
  const userTranscript = useLiveTutorStore((state) => state.userTranscript);
  const assistantTranscript = useLiveTutorStore((state) => state.assistantTranscript);
  const error = useLiveTutorStore((state) => state.error);
  const close = useLiveTutorStore((state) => state.close);
  const setStatus = useLiveTutorStore((state) => state.setStatus);
  const setMuted = useLiveTutorStore((state) => state.setMuted);
  const setUserTranscript = useLiveTutorStore((state) => state.setUserTranscript);
  const setAssistantTranscript = useLiveTutorStore((state) => state.setAssistantTranscript);
  const appendAssistantTranscript = useLiveTutorStore((state) => state.appendAssistantTranscript);
  const setError = useLiveTutorStore((state) => state.setError);
  const resetTranscript = useLiveTutorStore((state) => state.resetTranscript);

  const addUserMessage = useChatStore((state) => state.addUserMessage);
  const addAssistantMessage = useChatStore((state) => state.addAssistantMessage);
  const updateAssistantMessage = useChatStore((state) => state.updateAssistantMessage);
  const createConversation = useConversationStore((state) => state.createConversation);
  const selectConversation = useConversationStore((state) => state.selectConversation);

  useEffect(() => {
    if (activeConversationId && !conversationIdRef.current) {
      conversationIdRef.current = activeConversationId;
    }
  }, [activeConversationId]);

  const ensureConversationId = useCallback(async (): Promise<string> => {
    if (conversationIdRef.current) return conversationIdRef.current;
    const currentActiveConversationId = useConversationStore.getState().activeConversationId;
    if (currentActiveConversationId) {
      conversationIdRef.current = currentActiveConversationId;
      return currentActiveConversationId;
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

  const persistTranscript = useCallback(async (
    role: 'user' | 'assistant',
    content: string,
  ) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    const conversationId = await ensureConversationId();
    if (role === 'user') {
      const userMessageId = addUserMessage(trimmed, conversationId);
      bumpConversationPreview(conversationId, trimmed);
      if (canPersistHistory()) {
        await databaseService.message.add(conversationId, {
          id: userMessageId,
          role: 'user',
          content: trimmed,
        });
      }
      return;
    }

    const assistantMessageId = assistantMessageIdRef.current ?? addAssistantMessage(conversationId);
    assistantMessageIdRef.current = null;
    updateAssistantMessage(assistantMessageId, {
      content: trimmed,
      isStreaming: false,
    });
    bumpConversationPreview(conversationId, trimmed);
    if (canPersistHistory()) {
      await databaseService.message.add(conversationId, {
        id: assistantMessageId,
        role: 'assistant',
        content: trimmed,
      });
    }
  }, [addAssistantMessage, addUserMessage, bumpConversationPreview, ensureConversationId, updateAssistantMessage]);

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
    resetTranscript();
    setError(null);
    const conversationId = await ensureConversationId();
    const controller = await startRealtimeClient({
      conversationId,
      interfaceLanguage: language,
      recentMessages: () => useChatStore.getState().messages
        .filter((message: DisplayMessage) => message.conversationId === conversationId),
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
        setAssistantTranscript('');
      },
      onUserTranscript: (transcript) => {
        if (isCancelledRef.current) return;
        finalizeAssistantDraft(conversationId);
        setUserTranscript(transcript);
        void persistTranscript('user', transcript);
      },
      onAssistantTranscriptDelta: (delta) => {
        if (isCancelledRef.current) return;
        if (!assistantMessageIdRef.current) {
          assistantMessageIdRef.current = addAssistantMessage(conversationId);
        }
        assistantTranscriptRef.current += delta;
        appendAssistantTranscript(delta);
        updateAssistantMessage(assistantMessageIdRef.current, {
          content: assistantTranscriptRef.current,
          isStreaming: true,
        });
      },
      onAssistantTranscriptDone: (transcript) => {
        if (isCancelledRef.current) return;
        setAssistantTranscript(transcript);
        finalizeAssistantDraft(conversationId, transcript);
      },
      onError: (nextError) => {
        if (isCancelledRef.current) return;
        const message = isMicrophonePermissionError(nextError)
          ? labels.permissionDenied
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
    appendAssistantTranscript,
    addAssistantMessage,
    ensureConversationId,
    finalizeAssistantDraft,
    labels.permissionDenied,
    labels.setupFailed,
    language,
    persistTranscript,
    resetTranscript,
    setAssistantTranscript,
    setError,
    setStatus,
    setUserTranscript,
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
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
    panelRef.current?.style.setProperty('--live-tutor-audio-level', '0');
    setStatus('idle');
  }, [finalizeAssistantDraft, setStatus]);

  const handleClose = useCallback(() => {
    stop();
    close();
  }, [close, stop]);

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

  const isActiveAudio = useMemo(() => (
    status === 'listening' || status === 'thinking' || status === 'speaking'
  ), [status]);

  if (!isOpen) return null;

  const primaryCaption = assistantTranscript || userTranscript || statusLabels[status];
  const captionText = error ? (assistantTranscript || userTranscript) : primaryCaption;
  const secondaryCaption = assistantTranscript && userTranscript ? userTranscript : '';

  return (
    <section ref={panelRef} className={styles.panel} aria-label={labels.title}>
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
        {captionText && (
          <div className={styles.captionArea}>
            <div className={styles.transcriptText}>{captionText}</div>
            {secondaryCaption && (
              <div className={styles.secondaryTranscript}>{secondaryCaption}</div>
            )}
          </div>
        )}

        {error && <div className={styles.error}>{error}</div>}

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
