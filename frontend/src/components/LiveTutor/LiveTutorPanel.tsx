'use client';

/**
 * AREQA Live Tutor voice panel.
 *
 * The panel owns the browser-only Realtime session and mirrors finalized voice
 * transcripts into the existing chat conversation. It does not feed audio
 * events into the text SSE stream, which keeps the original chat path stable.
 */

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { Mic, MicOff, PhoneOff, X } from 'lucide-react';
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
    close: '關閉',
    setupFailed: '無法啟動即時語音，請確認麥克風權限與 OpenAI Realtime 設定。',
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
    close: '关闭',
    setupFailed: '无法启动即时语音，请确认麦克风权限与 OpenAI Realtime 设置。',
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
    close: 'Close',
    setupFailed: 'Unable to start live voice. Check microphone permission and OpenAI Realtime configuration.',
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
}

export function LiveTutorPanel({ activeConversationId }: LiveTutorPanelProps) {
  const { styles, cx } = useStyles();
  const { language } = useUserPreferences();
  const labels = COPY[language];
  const statusLabels = STATUS_LABELS[language];
  const audioRef = useRef<HTMLAudioElement>(null);
  const controllerRef = useRef<RealtimeClientController | null>(null);
  const conversationIdRef = useRef<string>(activeConversationId || '');
  const assistantMessageIdRef = useRef<string | null>(null);
  const assistantTranscriptRef = useRef('');
  const hasStartedRef = useRef(false);

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

  const start = useCallback(async () => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    resetTranscript();
    setError(null);
    const conversationId = await ensureConversationId();
    controllerRef.current = await startRealtimeClient({
      conversationId,
      interfaceLanguage: language,
      recentMessages: () => useChatStore.getState().messages
        .filter((message: DisplayMessage) => message.conversationId === conversationId),
      onRemoteStream: (stream) => {
        if (audioRef.current) {
          audioRef.current.srcObject = stream;
          void audioRef.current.play();
        }
      },
      onStatus: (nextStatus: RealtimeStatus) => setStatus(nextStatus),
      onUserTranscript: (transcript) => {
        setUserTranscript(transcript);
        void persistTranscript('user', transcript);
      },
      onAssistantTranscriptDelta: (delta) => {
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
        setAssistantTranscript(transcript);
        assistantTranscriptRef.current = '';
        void persistTranscript('assistant', transcript);
      },
      onError: (nextError) => {
        setError(nextError.message || labels.setupFailed);
      },
    });
  }, [
    appendAssistantTranscript,
    addAssistantMessage,
    ensureConversationId,
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
    if (assistantMessageIdRef.current) {
      updateAssistantMessage(assistantMessageIdRef.current, {
        content: assistantTranscriptRef.current,
        isStreaming: false,
      });
    }
    controllerRef.current?.disconnect();
    controllerRef.current = null;
    hasStartedRef.current = false;
    assistantMessageIdRef.current = null;
    assistantTranscriptRef.current = '';
    setStatus('idle');
  }, [setStatus, updateAssistantMessage]);

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

  return (
    <div className={styles.overlay}>
      <section className={styles.panel} aria-label={labels.title}>
        <header className={styles.header}>
          <div className={styles.titleGroup}>
            <div className={styles.title}>{labels.title}</div>
            <div className={styles.status}>{statusLabels[status]}</div>
          </div>
          <Tooltip title={labels.close} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button type="button" className={styles.iconButton} onClick={handleClose} aria-label={labels.close}>
              <X size={18} />
            </button>
          </Tooltip>
        </header>

        <div className={styles.body}>
          <div className={styles.avatarStage}>
            <div className={styles.avatar}>
              {isActiveAudio && <span className={styles.avatarPulse} />}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo/areqa_icon_v4_A_text.png" alt="AREQA" className={styles.logo} />
            </div>
          </div>

          <div className={styles.wave} aria-hidden={!isActiveAudio}>
            <span />
            <span />
            <span />
            <span />
          </div>

          <div className={styles.transcript}>
            <div className={styles.transcriptBlock}>
              <div className={styles.transcriptLabel}>{labels.you}</div>
              <div className={styles.transcriptText}>{userTranscript || labels.emptyUser}</div>
            </div>
            <div className={styles.transcriptBlock}>
              <div className={styles.transcriptLabel}>{labels.areqa}</div>
              <div className={styles.transcriptText}>{assistantTranscript || labels.emptyAssistant}</div>
            </div>
          </div>
        </div>

        {error && <div className={styles.error}>{error}</div>}

        <div className={styles.controls}>
          <Tooltip title={isMuted ? labels.unmute : labels.mute} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button type="button" className={styles.primaryControl} onClick={handleMute} aria-label={isMuted ? labels.unmute : labels.mute}>
              {isMuted ? <MicOff size={22} /> : <Mic size={22} />}
            </button>
          </Tooltip>
          <Tooltip title={labels.end} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button type="button" className={cx(styles.endControl)} onClick={handleClose} aria-label={labels.end}>
              <PhoneOff size={22} />
            </button>
          </Tooltip>
        </div>

        <audio ref={audioRef} autoPlay />
      </section>
    </div>
  );
}

export default LiveTutorPanel;
