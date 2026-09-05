'use client';

/**
 * AREQA Live Tutor voice panel.
 *
 * The panel owns the browser-only Realtime shell. Realtime captures speech,
 * performs turn detection, and renders audio, while AREQA's existing `/stream`
 * path remains the authoritative answer source for visible chat content.
 */

import React, { useCallback, useEffect, useRef } from 'react';
import { RotateCcw } from 'lucide-react';
import Image from 'next/image';
import { Tooltip } from 'antd';
import { useStyles } from './styles';
import {
  RealtimeClientError,
  playLiveVoiceCue,
  startRealtimeClient,
  type RealtimeClientController,
} from '@/services/realtime';
import { useChatStore } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useLiveTutorStore } from '@/store/liveTutor';
import { cancelCurrentStream, sendMessage } from '@/services/chat';
import { generateUUID } from '@/utils/id';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';
import { selectLiveTutorConversationId, selectLiveTutorMessages } from './session';
import { normalizeVoiceTranscript } from '@/services/realtime/language';

const COPY = {
  'zh-TW': {
    title: 'AREQA 即時語音',
    connecting: 'Connecting',
    lostConnection: 'Lost Connection',
    retry: '重新連線',
    permissionDenied: '麥克風權限已被封鎖，請在瀏覽器網站設定中允許後重試。',
    insecureContext: '麥克風只能在 HTTPS 安全連線中使用。',
    microphoneUnavailable: '找不到可用的麥克風。',
    microphoneBusy: '麥克風目前無法使用，請關閉其他錄音程式後重試。',
    setupFailed: '無法啟動即時語音，請確認麥克風權限、OpenAI Realtime 權限或稍後再試。',
  },
  'zh-CN': {
    title: 'AREQA 即时语音',
    connecting: 'Connecting',
    lostConnection: 'Lost Connection',
    retry: '重新连接',
    permissionDenied: '麦克风权限已被阻止，请在浏览器网站设置中允许后重试。',
    insecureContext: '麦克风只能在 HTTPS 安全连接中使用。',
    microphoneUnavailable: '找不到可用的麦克风。',
    microphoneBusy: '麦克风目前无法使用，请关闭其他录音程序后重试。',
    setupFailed: '无法启动即时语音，请确认麦克风权限、OpenAI Realtime 权限或稍后再试。',
  },
  en: {
    title: 'AREQA Live Voice',
    connecting: 'Connecting',
    lostConnection: 'Lost Connection',
    retry: 'Reconnect',
    permissionDenied: 'Microphone access is blocked. Allow it in browser site settings, then retry.',
    insecureContext: 'Microphone access requires a secure HTTPS connection.',
    microphoneUnavailable: 'No microphone is available.',
    microphoneBusy: 'The microphone is unavailable. Close other recording apps and retry.',
    setupFailed: 'Unable to start live voice. Check microphone permission, OpenAI Realtime access, or try again later.',
  },
} as const;

export interface LiveTutorPanelProps {
  activeConversationId?: string | null;
  hasMessages?: boolean;
}

/**
 * Renders and owns one conversation-bound browser Realtime voice session.
 *
 * User transcripts are forwarded to `sendMessage()` so the normal chat stream,
 * persistence, memory, search policy, and rendering pipeline own the final
 * answer. Realtime transcript deltas from the spoken rendering reveal the
 * visible answer like subtitles, while persistence still uses AREQA's
 * authoritative text.
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
  const transcriptQueueRef = useRef<Promise<void>>(Promise.resolve());
  const playbackRef = useRef<'waiting' | 'playing' | 'finished' | 'interrupted'>('waiting');
  const inputLevelRef = useRef(0);
  const outputLevelRef = useRef(0);
  const turnSequenceRef = useRef(0);
  const pendingVoiceFinalizeRef = useRef<((displayContent?: string) => Promise<void>) | null>(null);
  const pendingVoiceAnswerRef = useRef('');
  const spokenTranscriptRef = useRef('');
  const hasPlayedConnectedCueRef = useRef(false);
  const hasSyncedInitialMuteRef = useRef(false);
  const hasStartedRef = useRef(false);
  const isCancelledRef = useRef(false);

  const isOpen = useLiveTutorStore((state) => state.isOpen);
  const isMuted = useLiveTutorStore((state) => state.isMuted);
  const error = useLiveTutorStore((state) => state.error);
  const status = useLiveTutorStore((state) => state.status);
  const closeRequestId = useLiveTutorStore((state) => state.closeRequestId);
  const close = useLiveTutorStore((state) => state.close);
  const setStatus = useLiveTutorStore((state) => state.setStatus);
  const setError = useLiveTutorStore((state) => state.setError);
  const resetTranscript = useLiveTutorStore((state) => state.resetTranscript);

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

  const enqueueTranscriptWork = useCallback((work: () => Promise<void>): void => {
    transcriptQueueRef.current = transcriptQueueRef.current
      .then(work)
      .catch((queueError) => {
        logger.error(
          'realtime.areqa_voice_turn_failed',
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

  const findLatestAssistantAnswer = useCallback((conversationId?: string | null): string => {
    const candidates = [...useChatStore.getState().messages].reverse();
    const message = candidates.find((item) => (
      item.role === 'assistant'
      && !item.isStreaming
      && item.content.trim().length > 0
      && (!conversationId || item.conversationId === conversationId)
    ));
    return message?.content.trim() ?? '';
  }, []);

  const runAreqaAuthoredTurn = useCallback(async (transcript: string): Promise<void> => {
    const normalizedTranscript = normalizeVoiceTranscript(transcript, language).trim();
    if (!normalizedTranscript || isCancelledRef.current) return;
    const turnId = ++turnSequenceRef.current;
    const conversationId = persistedConversationIdRef.current || activeConversationId || undefined;
    logger.info('realtime.areqa_voice_turn_started', {
      component: 'LiveTutorPanel',
      conversationId: conversationId ?? 'new',
      transcriptChars: normalizedTranscript.length,
    });
    const result = await sendMessage(normalizedTranscript, conversationId, [], {
      responseMode: 'voice',
      onVoiceContentChunk: () => undefined,
    });
    if (isCancelledRef.current || turnSequenceRef.current !== turnId || !result.completed) return;
    const answerConversationId = result.conversationId || useConversationStore.getState().activeConversationId || conversationId;
    if (answerConversationId) {
      persistedConversationIdRef.current = answerConversationId;
      conversationIdRef.current = answerConversationId;
    }
    pendingVoiceFinalizeRef.current = result.finalizeVoiceResponse ?? null;
    pendingVoiceAnswerRef.current = result.answerContent?.trim() ?? '';
    spokenTranscriptRef.current = '';
    const answer = result.answerContent?.trim() || findLatestAssistantAnswer(answerConversationId);
    if (!answer) return;
    if (turnSequenceRef.current !== turnId) return;
    controllerRef.current?.speakAreqaAnswer(answer);
    logger.info('realtime.areqa_voice_turn_ready_for_speech', {
      component: 'LiveTutorPanel',
      conversationId: answerConversationId ?? 'unknown',
      answerChars: answer.length,
    });
  }, [activeConversationId, findLatestAssistantAnswer, language]);

  const start = useCallback(async () => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    isCancelledRef.current = false;
    conversationIdRef.current = '';
    persistedConversationIdRef.current = '';
    transcriptQueueRef.current = Promise.resolve();
    resetTranscript();
    playbackRef.current = 'waiting';
    inputLevelRef.current = 0;
    outputLevelRef.current = 0;
    turnSequenceRef.current = 0;
    pendingVoiceFinalizeRef.current = null;
    pendingVoiceAnswerRef.current = '';
    spokenTranscriptRef.current = '';
    hasPlayedConnectedCueRef.current = false;
    hasSyncedInitialMuteRef.current = false;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
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
      onUserSpeechStarted: () => {
        if (isCancelledRef.current) return;
        const currentStatus = useLiveTutorStore.getState().status;
        if (currentStatus === 'connecting' || currentStatus === 'idle') {
          logger.info('realtime.voice_speech_ignored_before_ready', {
            component: 'LiveTutorPanel',
            status: currentStatus,
            conversationId: persistedConversationIdRef.current || conversationId,
          });
          return;
        }
        turnSequenceRef.current += 1;
        playbackRef.current = 'interrupted';
        controllerRef.current?.cancelSpeech();
        void cancelCurrentStream();
      },
      onStatus: (nextStatus) => {
        if (isCancelledRef.current) return;
        setStatus(nextStatus);
        if ((nextStatus === 'connected' || nextStatus === 'listening') && !hasPlayedConnectedCueRef.current) {
          hasPlayedConnectedCueRef.current = true;
          playLiveVoiceCue('connected');
        }
      },
      onAssistantResponseStarted: () => {
        if (!isCancelledRef.current) playbackRef.current = 'waiting';
      },
      onPlaybackState: (state) => {
        if (isCancelledRef.current) return;
        playbackRef.current = state === 'started' ? 'playing' : state === 'stopped' ? 'finished' : 'interrupted';
        if (state === 'stopped' && pendingVoiceFinalizeRef.current) {
          const finalize = pendingVoiceFinalizeRef.current;
          pendingVoiceFinalizeRef.current = null;
          void finalize(spokenTranscriptRef.current || pendingVoiceAnswerRef.current || undefined);
        }
      },
      onUserTranscript: (transcript) => {
        if (isCancelledRef.current) return;
        const currentStatus = useLiveTutorStore.getState().status;
        if (currentStatus !== 'listening') {
          logger.info('realtime.voice_transcript_ignored_before_ready', {
            component: 'LiveTutorPanel',
            status: currentStatus,
            conversationId: persistedConversationIdRef.current || conversationId,
            transcriptChars: transcript.trim().length,
          });
          return;
        }
        enqueueTranscriptWork(async () => {
          await runAreqaAuthoredTurn(transcript);
        });
      },
      onAssistantTranscriptDelta: (delta) => {
        if (isCancelledRef.current || !delta) return;
        spokenTranscriptRef.current += delta;
        useChatStore.getState().appendContent(delta);
      },
      onAssistantTranscriptDone: (transcript) => {
        if (isCancelledRef.current) return;
        const finalize = pendingVoiceFinalizeRef.current;
        pendingVoiceFinalizeRef.current = null;
        spokenTranscriptRef.current = transcript || spokenTranscriptRef.current;
        pendingVoiceAnswerRef.current = '';
        void finalize?.(spokenTranscriptRef.current);
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
    hasSyncedInitialMuteRef.current = true;
  }, [
    enqueueTranscriptWork,
    labels.insecureContext,
    labels.microphoneBusy,
    labels.microphoneUnavailable,
    labels.permissionDenied,
    labels.setupFailed,
    language,
    prepareSessionConversationId,
    resetTranscript,
    runAreqaAuthoredTurn,
    setError,
    setStatus,
    updateAudioScale,
  ]);

  const stop = useCallback(() => {
    isCancelledRef.current = true;
    turnSequenceRef.current += 1;
    playbackRef.current = 'interrupted';
    controllerRef.current?.cancelSpeech();
    controllerRef.current?.disconnect();
    void cancelCurrentStream();
    controllerRef.current = null;
    pendingVoiceFinalizeRef.current = null;
    pendingVoiceAnswerRef.current = '';
    spokenTranscriptRef.current = '';
    hasPlayedConnectedCueRef.current = false;
    hasSyncedInitialMuteRef.current = false;
    hasStartedRef.current = false;
    inputLevelRef.current = 0;
    outputLevelRef.current = 0;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
    setStatus('idle');
  }, [setStatus]);

  const handleClose = useCallback(() => {
    playLiveVoiceCue('hangup');
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
    if (!isOpen || !controllerRef.current) return;
    if (!hasSyncedInitialMuteRef.current) {
      hasSyncedInitialMuteRef.current = true;
      return;
    }
    playLiveVoiceCue(isMuted ? 'muted' : 'unmuted');
  }, [isMuted, isOpen]);

  useEffect(() => {
    if (!isOpen || closeRequestId === 0) return;
    handleClose();
  }, [closeRequestId, handleClose, isOpen]);

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
        {status === 'connecting' && !error && (
          <div className={styles.statusText}>{labels.connecting}</div>
        )}

        {error && (
          <div className={styles.errorRow}>
            <div className={styles.error}>{labels.lostConnection}</div>
            <Tooltip title={labels.retry} color="#262626" styles={{ container: { color: '#ffffff' } }}>
              <button type="button" className={styles.retryButton} onClick={handleRetry} aria-label={labels.retry}>
                <RotateCcw size={17} />
              </button>
            </Tooltip>
          </div>
        )}

        {status !== 'connecting' && !error && (
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
        )}
      </div>

      <audio ref={audioRef} autoPlay />
    </section>
  );
}

export default LiveTutorPanel;
