'use client';

/**
 * AREQA Live Tutor voice panel.
 *
 * The panel owns the browser-only Realtime session. Realtime is the primary
 * live voice agent, while AREQA app context is exposed through a bounded tool
 * so the experience can respond immediately instead of waiting for `/stream`.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { Tooltip } from 'antd';
import { useStyles } from './styles';
import { FloatingAvatarWindow } from './FloatingAvatarWindow';
import { LiveTutorAvatarStage } from './LiveTutorAvatarStage';
import {
  RealtimeClientError,
  playLiveVoiceCue,
  startLiveKitAvatarClient,
  startRealtimeClient,
  type RealtimeClientController,
} from '@/services/realtime';
import { useChatStore, type TutorProfile } from '@/store/chat';
import { useConversationStore } from '@/store/conversation';
import { useLiveTutorStore } from '@/store/liveTutor';
import { databaseService } from '@/services/database';
import { getCurrentUserId } from '@/database/db';
import { cancelCurrentStream, sendMessage } from '@/services/chat';
import { generateUUID } from '@/utils/id';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';
import { selectLiveTutorConversationId, selectLiveTutorMessages } from './session';
import { normalizeVoiceTranscript } from '@/services/realtime/language';
import { shouldCreateImageForVoiceTurn } from '@/services/realtime/imageIntent';
import { generateConversationImage } from '@/services/generatedImages';
import { shouldDelegateEnglishSpeakingTurn, shouldDelegateVoiceTurnToDeepAnswer } from '@/services/realtime/deepDelegation';
import { normalizeReadbackText } from '@/services/realtime/readbackText';
import { loadVoiceMaterial, prepareVoiceAttachments } from '@/services/realtime/attachments';
import { filesToAttachmentMetadata } from '@/utils/attachments';

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
    avatarFallback: '虛擬角色啟動失敗，已切回語音模式。',
    deepAnswerHold: '我先整理一下重點，等我一下。',
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
    avatarFallback: '虚拟角色启动失败，已切回语音模式。',
    deepAnswerHold: '我先整理一下重点，等我一下。',
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
    avatarFallback: 'Avatar could not start. Switched back to voice mode.',
    deepAnswerHold: 'I will organize the key points first. Give me a moment.',
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
  layout?: 'inline' | 'side-pane';
}

/**
 * Renders and owns one conversation-bound browser Realtime voice session.
 *
 * Finalized user transcripts and assistant audio transcripts are mirrored into
 * the normal chat store. Deep document or learning requests also run through
 * the established AREQA chat stream in voice mode so the visible answer can use
 * the same grounded backend pipeline as text chat while Realtime keeps owning
 * immediate speech and interruptions.
 *
 * @param props - Active conversation and whether normal messages are visible.
 * @returns The inline voice panel, or `null` while voice mode is closed.
 */
export function LiveTutorPanel({ activeConversationId, hasMessages = false, layout = 'inline' }: LiveTutorPanelProps) {
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
  const assistantTurnGenerationRef = useRef(0);
  const learnerTurnGenerationRef = useRef(0);
  const speechEpochRef = useRef(0);
  const userSpeakingRef = useRef(false);
  const speechEpochByItemRef = useRef(new Map<string, number>());
  const activeAssistantResponseIdRef = useRef<string | null>(null);
  const staleAssistantResponseIdsRef = useRef(new Set<string>());
  const lastVoiceMessageIdRef = useRef<string | null>(null);
  const userTurnIdsRef = useRef(new Map<string, string>());
  const imageTurnIdsRef = useRef(new Set<string>());
  const delegatedDeepAnswerActiveRef = useRef(false);
  const speakingPracticeActiveRef = useRef(false);
  const backendReadbackActiveRef = useRef(false);
  const attachmentGenerationRef = useRef(0);
  const attachmentUploadInProgressRef = useRef(false);
  const playbackRef = useRef<'waiting' | 'playing' | 'finished' | 'interrupted'>('waiting');
  const inputLevelRef = useRef(0);
  const outputLevelRef = useRef(0);
  const hasPlayedConnectedCueRef = useRef(false);
  const hasSyncedInitialMuteRef = useRef(false);
  const hasStartedRef = useRef(false);
  const isCancelledRef = useRef(false);
  const sessionGenerationRef = useRef(0);
  const activeProviderRef = useRef<'openai_realtime' | 'livekit_anam' | null>(null);
  const activeTutorProfileRef = useRef<TutorProfile | null>(null);
  const reconfigurePromiseRef = useRef<Promise<void> | null>(null);
  const pendingAvatarNoticeRef = useRef<string | null>(null);
  const [avatarVideoStream, setAvatarVideoStream] = useState<MediaStream | null>(null);
  const [avatarNotice, setAvatarNotice] = useState<string | null>(null);

  const isOpen = useLiveTutorStore((state) => state.isOpen);
  const isMuted = useLiveTutorStore((state) => state.isMuted);
  const avatarEnabled = useLiveTutorStore((state) => state.avatarEnabled);
  const error = useLiveTutorStore((state) => state.error);
  const status = useLiveTutorStore((state) => state.status);
  const closeRequestId = useLiveTutorStore((state) => state.closeRequestId);
  const close = useLiveTutorStore((state) => state.close);
  const setStatus = useLiveTutorStore((state) => state.setStatus);
  const setError = useLiveTutorStore((state) => state.setError);
  const setSendVoiceMessage = useLiveTutorStore((state) => state.setSendVoiceMessage);
  const resetTranscript = useLiveTutorStore((state) => state.resetTranscript);
  const addUserMessage = useChatStore((state) => state.addUserMessage);
  const addAssistantMessage = useChatStore((state) => state.addAssistantMessage);
  const updateAssistantMessage = useChatStore((state) => state.updateAssistantMessage);
  const tutorProfile = useChatStore((state) => state.tutorProfile);
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

  const invalidateAssistantTurn = useCallback((): number => {
    assistantTurnGenerationRef.current += 1;
    if (activeAssistantResponseIdRef.current) {
      staleAssistantResponseIdsRef.current.add(activeAssistantResponseIdRef.current);
    }
    activeAssistantResponseIdRef.current = null;
    return assistantTurnGenerationRef.current;
  }, []);

  const isCurrentAssistantTurn = useCallback((generation: number, responseId?: string): boolean => {
    if (generation !== assistantTurnGenerationRef.current) return false;
    if (!responseId) return true;
    if (staleAssistantResponseIdsRef.current.has(responseId)) return false;
    return Boolean(activeAssistantResponseIdRef.current && responseId === activeAssistantResponseIdRef.current);
  }, []);

  const invalidateLearnerTurn = useCallback((): number => {
    learnerTurnGenerationRef.current += 1;
    return learnerTurnGenerationRef.current;
  }, []);

  const isCurrentLearnerTurn = useCallback((generation: number): boolean => (
    generation === learnerTurnGenerationRef.current
  ), []);

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
        authenticated: isAuthenticated,
      });
      return persistedConversationId;
    })();

    try {
      return await conversationMaterializationRef.current;
    } finally {
      conversationMaterializationRef.current = null;
    }
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

  const sendVoiceMessage = useCallback(async (content: string, files: File[]) => {
    if (attachmentUploadInProgressRef.current) throw new Error('An attachment is already uploading');
    attachmentUploadInProgressRef.current = true;
    try {
      const generation = files.length
        ? ++attachmentGenerationRef.current
        : attachmentGenerationRef.current;
      const conversationId = await ensurePersistedConversationId();
      const prepared = files.length ? await prepareVoiceAttachments(conversationId, files) : null;
      if (isCancelledRef.current || generation !== attachmentGenerationRef.current
        || persistedConversationIdRef.current !== conversationId) {
        throw new Error('Voice conversation changed during attachment upload');
      }
      const controller = controllerRef.current;
      if (!controller) throw new Error('Voice session is not ready');
      if (prepared && content.trim()) controller.cancelSpeech();
      const delivered = prepared
        ? await controller?.addAttachmentContext?.(prepared.material, content)
        : await controller?.sendUserText?.(content);
      if (!delivered) {
        throw new Error('Voice session could not receive the message');
      }
      const displayContent = content.trim() || '已上傳檔案';
      const metadata = filesToAttachmentMetadata(files);
      const id = addUserMessage(displayContent, conversationId, metadata);
      bumpConversationPreview(conversationId, displayContent);
      if (canPersistHistory()) {
        void databaseService.message.add(conversationId, {
          id,
          role: 'user',
          content: displayContent,
          ...(metadata.length ? { attachments: metadata } : {}),
        }).catch((error) => logger.warn('realtime.attachment_message_persistence_failed', {
          conversationId,
          errorName: error instanceof Error ? error.name : 'UnknownError',
        }));
      }
      if (prepared && content.trim() && activeProviderRef.current === 'openai_realtime') {
        controller.requestResponse?.();
      }
      logger.info('realtime.voice_message_delivered', {
        conversationId,
        version: prepared?.version ?? null,
        fileCount: files.length,
        excerptChars: prepared?.material.text.length ?? 0,
      });
      return { completed: true };
    } finally {
      attachmentUploadInProgressRef.current = false;
    }
  }, [addUserMessage, bumpConversationPreview, ensurePersistedConversationId]);

  useEffect(() => {
    if (!isOpen) return;
    setSendVoiceMessage(sendVoiceMessage);
    return () => setSendVoiceMessage(null);
  }, [isOpen, setSendVoiceMessage, sendVoiceMessage]);

  const persistUserTranscript = useCallback(async (content: string, itemId?: string): Promise<void> => {
    const normalized = normalizeVoiceTranscript(content, language).trim();
    if (!normalized || isCancelledRef.current) return;

    const conversationId = await ensurePersistedConversationId();
    const pendingId = itemId ? userTurnIdsRef.current.get(itemId) : undefined;
    const userMessageId = pendingId ?? addUserMessage(normalized, conversationId);
    if (pendingId) useChatStore.getState().updateMessageContent(pendingId, normalized);
    if (itemId) userTurnIdsRef.current.delete(itemId);
    bumpConversationPreview(conversationId, normalized);

    if (canPersistHistory()) {
      void databaseService.message.add(conversationId, {
        id: userMessageId,
        role: 'user',
        content: normalized,
        createdAt: useChatStore.getState().messages.find((message) => message.id === userMessageId)?.createdAt,
      }).catch((error) => {
        logger.warn('realtime.user_transcript_persistence_failed', {
          component: 'LiveTutorPanel',
          conversationId,
          errorName: error instanceof Error ? error.name : 'UnknownError',
        });
      });
    }
  }, [addUserMessage, bumpConversationPreview, ensurePersistedConversationId, language]);

  const finalizeAssistantDraft = useCallback(async (
    contentOverride?: string,
    options: {
      messageId?: string | null;
      playback?: typeof playbackRef.current;
      clearDraftRefs?: boolean;
    } = {},
  ): Promise<void> => {
    const content = normalizeVoiceTranscript(contentOverride ?? assistantTranscriptRef.current, language).trim();
    if (!content) {
      if (options.clearDraftRefs !== false) {
        assistantMessageIdRef.current = null;
        assistantTranscriptRef.current = '';
      }
      return;
    }

    const conversationId = await ensurePersistedConversationId();
    const assistantMessageId = options.messageId || assistantMessageIdRef.current || addAssistantMessage(conversationId);
    lastVoiceMessageIdRef.current = assistantMessageId;
    updateAssistantMessage(assistantMessageId, {
      conversationId,
      content,
      isStreaming: false,
      voicePlayback: options.playback ?? (playbackRef.current === 'waiting' ? 'finished' : playbackRef.current),
    });
    if (options.clearDraftRefs !== false) {
      assistantMessageIdRef.current = null;
      assistantTranscriptRef.current = '';
    }
    bumpConversationPreview(conversationId, content);

    if (canPersistHistory()) {
      void databaseService.message.add(conversationId, {
        id: assistantMessageId,
        role: 'assistant',
        content,
        createdAt: useChatStore.getState().messages.find((message) => message.id === assistantMessageId)?.createdAt,
      }).catch(() => undefined);
    }
  }, [addAssistantMessage, bumpConversationPreview, ensurePersistedConversationId, language, updateAssistantMessage]);

  const appendAssistantTranscript = useCallback(async (delta: string): Promise<void> => {
    if (!delta) return;

    assistantTranscriptRef.current += delta;
    const conversationId = persistedConversationIdRef.current || conversationIdRef.current || prepareSessionConversationId();
    if (!assistantMessageIdRef.current) {
      assistantMessageIdRef.current = addAssistantMessage(conversationId);
    }
    lastVoiceMessageIdRef.current = assistantMessageIdRef.current;
    updateAssistantMessage(assistantMessageIdRef.current, {
      content: normalizeVoiceTranscript(assistantTranscriptRef.current, language),
      isStreaming: true,
      voicePlayback: playbackRef.current,
    });
  }, [addAssistantMessage, language, prepareSessionConversationId, updateAssistantMessage]);

  const updateAudioScale = useCallback(() => {
    const level = Math.max(inputLevelRef.current, outputLevelRef.current);
    const scale = 1 + Math.min(Math.max(level, 0), 1) * 0.18;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', scale.toFixed(3));
  }, []);

  const start = useCallback(async () => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    isCancelledRef.current = false;
    imageTurnIdsRef.current.clear();
    const sessionGeneration = ++sessionGenerationRef.current;
    const isCurrentSession = () => !isCancelledRef.current && sessionGeneration === sessionGenerationRef.current;
    conversationIdRef.current = '';
    persistedConversationIdRef.current = '';
    conversationMaterializationRef.current = null;
    transcriptQueueRef.current = Promise.resolve();
    resetTranscript();
    playbackRef.current = 'waiting';
    inputLevelRef.current = 0;
    outputLevelRef.current = 0;
    setAvatarVideoStream(null);
    setAvatarNotice(pendingAvatarNoticeRef.current);
    pendingAvatarNoticeRef.current = null;
    assistantMessageIdRef.current = null;
    assistantTranscriptRef.current = '';
    staleAssistantResponseIdsRef.current.clear();
    invalidateAssistantTurn();
    lastVoiceMessageIdRef.current = null;
    userTurnIdsRef.current.clear();
    speechEpochRef.current = 0;
    userSpeakingRef.current = false;
    speechEpochByItemRef.current.clear();
    delegatedDeepAnswerActiveRef.current = false;
    speakingPracticeActiveRef.current = false;
    backendReadbackActiveRef.current = false;
    hasPlayedConnectedCueRef.current = false;
    hasSyncedInitialMuteRef.current = false;
    const selectedProvider = useLiveTutorStore.getState().avatarEnabled ? 'livekit_anam' : 'openai_realtime';
    const selectedTutorProfile = useChatStore.getState().tutorProfile;
    activeProviderRef.current = selectedProvider;
    activeTutorProfileRef.current = selectedTutorProfile;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
    setError(null);
    const conversationId = prepareSessionConversationId();
    logger.info('realtime.voice_session_bound', {
      component: 'LiveTutorPanel',
      conversationId,
      provider: selectedProvider,
      tutorProfile: selectedTutorProfile,
      contextMessageCount: selectLiveTutorMessages(useChatStore.getState().messages, conversationId).length,
      isPersistedConversation: persistedConversationIdRef.current === conversationId,
    });
    const startProviderClient = selectedProvider === 'livekit_anam'
      ? startLiveKitAvatarClient
      : startRealtimeClient;
    const controller = await startProviderClient({
      conversationId,
      getConversationId: () => persistedConversationIdRef.current || conversationId,
      interfaceLanguage: language,
      tutorProfile: selectedTutorProfile,
      recentMessages: () => selectLiveTutorMessages(
        useChatStore.getState().messages,
        persistedConversationIdRef.current || conversationId,
      ),
      onRemoteStream: (stream) => {
        if (!isCurrentSession()) return;
        if (audioRef.current) {
          audioRef.current.srcObject = stream;
          void audioRef.current.play();
        }
      },
      onRemoteVideoStream: (stream) => {
        if (!isCurrentSession()) return;
        setAvatarVideoStream(stream);
        if (!stream) {
          logger.warn('realtime.avatar_video_stream_cleared', {
            component: 'LiveTutorPanel',
            conversationId: persistedConversationIdRef.current || conversationId,
            provider: selectedProvider,
          });
          return;
        }
        logger.info('realtime.avatar_video_stream_received', {
          component: 'LiveTutorPanel',
          conversationId: persistedConversationIdRef.current || conversationId,
          provider: selectedProvider,
          videoTrackCount: stream.getVideoTracks().length,
        });
      },
      onInputAudioLevel: (level) => {
        if (!isCurrentSession()) return;
        inputLevelRef.current = Math.min(Math.max(level, 0), 1);
        updateAudioScale();
      },
      onOutputAudioLevel: (level) => {
        if (!isCurrentSession()) return;
        outputLevelRef.current = Math.min(Math.max(level, 0), 1);
        updateAudioScale();
      },
      onUserSpeechStarted: (itemId) => {
        if (!isCurrentSession()) return;
        const currentStatus = useLiveTutorStore.getState().status;
        if (currentStatus === 'connecting' || currentStatus === 'idle') {
          logger.info('realtime.voice_speech_ignored_before_ready', {
            component: 'LiveTutorPanel',
            status: currentStatus,
            conversationId: persistedConversationIdRef.current || conversationId,
          });
          return;
        }
        speechEpochRef.current += 1;
        userSpeakingRef.current = true;
        if (itemId) speechEpochByItemRef.current.set(itemId, speechEpochRef.current);
        playbackRef.current = 'interrupted';
        invalidateLearnerTurn();
        invalidateAssistantTurn();
        delegatedDeepAnswerActiveRef.current = false;
        backendReadbackActiveRef.current = false;
        controllerRef.current?.cancelSpeech();
        void cancelCurrentStream();
      },
      onStatus: (nextStatus) => {
        if (!isCurrentSession()) return;
        setStatus(nextStatus);
        if ((nextStatus === 'connected' || nextStatus === 'listening') && !hasPlayedConnectedCueRef.current) {
          hasPlayedConnectedCueRef.current = true;
          playLiveVoiceCue('connected');
        }
      },
      onAssistantResponseStarted: (responseId) => {
        if (!isCurrentSession()) return;
        assistantTurnGenerationRef.current += 1;
        activeAssistantResponseIdRef.current = responseId || null;
        if (responseId) staleAssistantResponseIdsRef.current.delete(responseId);
        const responseGeneration = assistantTurnGenerationRef.current;
        if (backendReadbackActiveRef.current) {
          playbackRef.current = 'waiting';
          return;
        }
        if (delegatedDeepAnswerActiveRef.current) {
          controllerRef.current?.cancelSpeech();
          logger.info('realtime.deep_answer_suppressed_realtime_reply', {
            component: 'LiveTutorPanel',
            conversationId: persistedConversationIdRef.current || conversationId,
            provider: selectedProvider,
          });
          return;
        }
        playbackRef.current = 'waiting';
        enqueueTranscriptWork(async () => {
          if (!isCurrentAssistantTurn(responseGeneration, responseId)) return;
          await finalizeAssistantDraft();
          lastVoiceMessageIdRef.current = null;
        });
      },
      onPlaybackState: (state) => {
        if (!isCurrentSession()) return;
        playbackRef.current = state === 'started' ? 'playing' : state === 'stopped' ? 'finished' : 'interrupted';
        if (state === 'stopped' || state === 'interrupted') {
          backendReadbackActiveRef.current = false;
        }
        const playback = playbackRef.current;
        enqueueTranscriptWork(async () => {
          if (lastVoiceMessageIdRef.current) {
            updateAssistantMessage(lastVoiceMessageIdRef.current, { voicePlayback: playback });
          }
        });
      },
      onUserTurnCommitted: (itemId) => {
        if (!isCurrentSession()) return;
        const turnEpoch = speechEpochByItemRef.current.get(itemId) ?? speechEpochRef.current;
        speechEpochByItemRef.current.set(itemId, turnEpoch);
        if (turnEpoch === speechEpochRef.current) userSpeakingRef.current = false;
        enqueueTranscriptWork(async () => {
          if (userTurnIdsRef.current.has(itemId)) return;
          const conversationId = await ensurePersistedConversationId();
          userTurnIdsRef.current.set(itemId, addUserMessage('', conversationId));
        });
      },
      onUserTranscript: (transcript, itemId) => {
        if (!isCurrentSession()) return;
        const currentStatus = useLiveTutorStore.getState().status;
        if (currentStatus === 'connecting' || currentStatus === 'idle') {
          logger.info('realtime.voice_transcript_ignored_before_ready', {
            component: 'LiveTutorPanel',
            status: currentStatus,
            conversationId: persistedConversationIdRef.current || conversationId,
            transcriptChars: transcript.trim().length,
          });
          return;
        }
        const transcriptEpoch = (itemId && speechEpochByItemRef.current.get(itemId)) ?? speechEpochRef.current;
        const transcriptReceivedAt = Date.now();
        const isSuperseded = () => transcriptEpoch !== speechEpochRef.current || userSpeakingRef.current;
        enqueueTranscriptWork(async () => {
          const normalized = normalizeVoiceTranscript(transcript, language).trim();
          if (!normalized) return;
          if (isSuperseded()) {
            await persistUserTranscript(normalized, itemId);
            logger.info('realtime.stale_user_turn_answer_skipped', {
              component: 'LiveTutorPanel',
              conversationId: persistedConversationIdRef.current || conversationId,
              transcriptAgeMs: Date.now() - transcriptReceivedAt,
            });
            return;
          }
          if (/(停止練習|结束练习|結束練習|stop practice|end practice)/i.test(normalized)) {
            speakingPracticeActiveRef.current = false;
          }

          const speakingPracticeTurn = selectedTutorProfile === 'english'
            && shouldDelegateEnglishSpeakingTurn(normalized, speakingPracticeActiveRef.current);
          const imageTurnKey = itemId || `${transcriptEpoch}:${normalized}`;
          if (canPersistHistory() && shouldCreateImageForVoiceTurn(normalized)
            && !imageTurnIdsRef.current.has(imageTurnKey) && !isSuperseded()) {
            imageTurnIdsRef.current.add(imageTurnKey);
            const imageConversationId = await ensurePersistedConversationId();
            // Image work is independent of the voice reply and must not stall speech.
            void generateConversationImage(normalized, imageConversationId, language, false)
              .then((result) => {
                if (!result.completed || !isCurrentSession() || userSpeakingRef.current) return;
                if (useLiveTutorStore.getState().status === 'speaking') return;
                controllerRef.current?.speakText(
                  result.block?.visionSummary
                    ? `${language === 'en' ? 'The image is ready. ' : '圖片已完成。'}${result.block.visionSummary}`
                    : language === 'en'
                      ? 'The image is ready. You can open it in the conversation while we continue.'
                      : '圖片已完成，可以在對話中打開查看，我們可以接著討論。',
                );
              })
              .catch((error) => logger.warn('realtime.image_generation_failed', {
                conversationId: imageConversationId,
                errorName: error instanceof Error ? error.name : 'UnknownError',
              }));
          }
          if (speakingPracticeTurn) speakingPracticeActiveRef.current = true;
          if (speakingPracticeTurn || shouldDelegateVoiceTurnToDeepAnswer(normalized)) {
            const pendingId = itemId ? userTurnIdsRef.current.get(itemId) : undefined;
            if (pendingId && itemId) {
              useChatStore.getState().removeMessage(pendingId);
              userTurnIdsRef.current.delete(itemId);
            }
            const persistedConversationId = await ensurePersistedConversationId();
            if (isSuperseded()) {
              await persistUserTranscript(normalized, itemId);
              return;
            }
            const deepGeneration = invalidateLearnerTurn();
            delegatedDeepAnswerActiveRef.current = true;
            lastVoiceMessageIdRef.current = null;
            controllerRef.current?.cancelSpeech();
            backendReadbackActiveRef.current = controllerRef.current?.speakText(labels.deepAnswerHold) ?? false;
            logger.info('realtime.deep_answer_started', {
              component: 'LiveTutorPanel',
              conversationId: persistedConversationId,
              provider: selectedProvider,
              transcriptChars: normalized.length,
              holdSpeechStarted: backendReadbackActiveRef.current,
            });
            try {
              const result = await sendMessage(normalized, persistedConversationId, [], {
                responseMode: 'voice',
                useRag: true,
                searchMode: 'auto',
                tutorProfile: selectedTutorProfile,
                speakingPractice: speakingPracticeTurn,
              });
              if (isCurrentSession() && isCurrentLearnerTurn(deepGeneration)) {
                const readbackText = normalizeReadbackText(result.answerContent ?? '');
                await result.finalizeVoiceResponse?.(readbackText);
              }
              const readbackText = normalizeReadbackText(result.answerContent ?? '');
              if (isCurrentSession() && isCurrentLearnerTurn(deepGeneration) && readbackText && result.assistantMessageId) {
                lastVoiceMessageIdRef.current = result.assistantMessageId;
                updateAssistantMessage(result.assistantMessageId, { voicePlayback: 'waiting' });
                const speechStarted = controllerRef.current?.speakText(readbackText) ?? false;
                backendReadbackActiveRef.current = speechStarted;
                if (!speechStarted) {
                  updateAssistantMessage(result.assistantMessageId, { voicePlayback: 'finished' });
                }
                logger.info('realtime.deep_answer_readback_requested', {
                  component: 'LiveTutorPanel',
                  conversationId: persistedConversationId,
                  provider: selectedProvider,
                  speechStarted,
                  answerChars: readbackText.length,
                });
              }
              logger.info('realtime.deep_answer_completed', {
                component: 'LiveTutorPanel',
                conversationId: persistedConversationId,
                stale: !isCurrentLearnerTurn(deepGeneration),
                completed: result.completed,
                answerChars: result.answerContent?.length ?? 0,
              });
            } catch (error) {
              if (isCurrentSession() && isCurrentLearnerTurn(deepGeneration)) {
                controllerRef.current?.cancelSpeech();
                backendReadbackActiveRef.current = false;
                setStatus('listening');
              }
              logger.warn('realtime.deep_answer_failed', {
                component: 'LiveTutorPanel',
                conversationId: persistedConversationId,
                errorName: error instanceof Error ? error.name : 'UnknownError',
              });
            } finally {
              if (isCurrentLearnerTurn(deepGeneration)) {
                delegatedDeepAnswerActiveRef.current = false;
              }
            }
            return;
          }

          await persistUserTranscript(normalized, itemId);
          if (selectedTutorProfile === 'english' && isCurrentSession() && !isSuperseded()) {
            controllerRef.current?.requestResponse?.();
            logger.info('realtime.voice_reply_requested', {
              component: 'LiveTutorPanel',
              conversationId: persistedConversationIdRef.current || conversationId,
              transcriptToReplyMs: Date.now() - transcriptReceivedAt,
            });
          }
        });
      },
      onAssistantTranscriptDelta: (delta, responseId) => {
        if (!isCurrentSession() || delegatedDeepAnswerActiveRef.current || backendReadbackActiveRef.current || !delta) return;
        const responseGeneration = assistantTurnGenerationRef.current;
        enqueueTranscriptWork(async () => {
          if (!isCurrentAssistantTurn(responseGeneration, responseId)) {
            logger.info('realtime.voice_stale_delta_ignored', {
              component: 'LiveTutorPanel',
              conversationId: persistedConversationIdRef.current || conversationId,
              provider: selectedProvider,
              responseId: responseId || null,
            });
            return;
          }
          await appendAssistantTranscript(delta);
        });
      },
      onAssistantTranscriptDone: (transcript, responseId) => {
        if (!isCurrentSession() || delegatedDeepAnswerActiveRef.current || backendReadbackActiveRef.current) return;
        const responseGeneration = assistantTurnGenerationRef.current;
        enqueueTranscriptWork(async () => {
          if (!isCurrentAssistantTurn(responseGeneration, responseId)) {
            logger.info('realtime.voice_stale_done_ignored', {
              component: 'LiveTutorPanel',
              conversationId: persistedConversationIdRef.current || conversationId,
              provider: selectedProvider,
              responseId: responseId || null,
              transcriptChars: transcript.trim().length,
            });
            return;
          }
          await finalizeAssistantDraft(transcript);
        });
      },
      onError: (nextError) => {
        if (!isCurrentSession()) return;
        if (selectedProvider === 'livekit_anam' && controllerRef.current) {
          logger.warn('livekit.avatar_runtime_fallback_to_realtime', {
            component: 'LiveTutorPanel',
            conversationId: persistedConversationIdRef.current || conversationId,
            errorName: nextError instanceof Error ? nextError.name : 'UnknownError',
          });
          pendingAvatarNoticeRef.current = labels.avatarFallback;
          setAvatarVideoStream(null);
          useLiveTutorStore.getState().setAvatarEnabled(false);
          return;
        }
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
        if (nextError instanceof RealtimeClientError && nextError.recoverable) {
          logger.warn('realtime.voice_provider_turn_failed', {
            component: 'LiveTutorPanel',
            conversationId: persistedConversationIdRef.current || conversationId,
            provider: selectedProvider,
          });
          return;
        }
        setError(message);
      },
    });
    if (!isCurrentSession() || !useLiveTutorStore.getState().isOpen) {
      controller.disconnect();
      return;
    }
    if (selectedProvider === 'livekit_anam' && useLiveTutorStore.getState().error) {
      controller.disconnect();
      logger.warn('livekit.avatar_fallback_to_realtime', {
        component: 'LiveTutorPanel',
        conversationId: persistedConversationIdRef.current || conversationId,
      });
      pendingAvatarNoticeRef.current = labels.avatarFallback;
      useLiveTutorStore.getState().setAvatarEnabled(false);
      setError(null);
      return;
    }
    controllerRef.current = controller;
    controller.setMuted(useLiveTutorStore.getState().isMuted);
    hasSyncedInitialMuteRef.current = true;
    const attachmentGeneration = attachmentGenerationRef.current;
    void loadVoiceMaterial(conversationId).then((material) => {
      if (!material || !isCurrentSession() || attachmentGeneration !== attachmentGenerationRef.current) return;
      return controller.addAttachmentContext?.(material);
    }).catch((error) => logger.warn('realtime.attachment_restore_failed', {
      conversationId,
      errorName: error instanceof Error ? error.name : 'UnknownError',
    }));
  }, [
    enqueueTranscriptWork,
    appendAssistantTranscript,
    finalizeAssistantDraft,
    invalidateAssistantTurn,
    invalidateLearnerTurn,
    isCurrentAssistantTurn,
    isCurrentLearnerTurn,
    labels.insecureContext,
    labels.microphoneBusy,
    labels.microphoneUnavailable,
    labels.permissionDenied,
    labels.setupFailed,
    labels.avatarFallback,
    labels.deepAnswerHold,
    language,
    prepareSessionConversationId,
    persistUserTranscript,
    resetTranscript,
    setError,
    setStatus,
    updateAudioScale,
    updateAssistantMessage,
    addUserMessage,
    ensurePersistedConversationId,
  ]);

  const stop = useCallback(async (): Promise<void> => {
    sessionGenerationRef.current += 1;
    attachmentGenerationRef.current += 1;
    isCancelledRef.current = true;
    userSpeakingRef.current = false;
    speechEpochByItemRef.current.clear();
    delegatedDeepAnswerActiveRef.current = false;
    backendReadbackActiveRef.current = false;
    playbackRef.current = 'interrupted';
    invalidateLearnerTurn();
    invalidateAssistantTurn();
    controllerRef.current?.cancelSpeech();
    controllerRef.current?.disconnect();
    void cancelCurrentStream();
    controllerRef.current = null;
    activeProviderRef.current = null;
    activeTutorProfileRef.current = null;
    const pendingTranscriptWork = transcriptQueueRef.current;
    const finalization = pendingTranscriptWork
      .then(async () => {
        const draft = assistantTranscriptRef.current;
        const draftMessageId = assistantMessageIdRef.current;
        const lastVoiceMessageId = lastVoiceMessageIdRef.current;
        const pendingUserTurnIds = Array.from(userTurnIdsRef.current.values());

        await finalizeAssistantDraft(draft, {
          messageId: draftMessageId,
          playback: draft.trim() ? 'interrupted' : undefined,
          clearDraftRefs: false,
        });
        if (!draft.trim() && lastVoiceMessageId) {
          updateAssistantMessage(lastVoiceMessageId, { voicePlayback: 'finished', isStreaming: false });
        }
        for (const id of pendingUserTurnIds) {
          useChatStore.getState().removeMessage(id);
        }
        assistantMessageIdRef.current = null;
        assistantTranscriptRef.current = '';
        lastVoiceMessageIdRef.current = null;
        userTurnIdsRef.current.clear();
        logger.info('realtime.voice_session_stopped', {
          component: 'LiveTutorPanel',
          hadAssistantDraft: Boolean(draft.trim()),
          pendingUserTurnCount: pendingUserTurnIds.length,
        });
      })
      .catch((queueError) => {
        logger.error(
          'realtime.transcript_persistence_failed',
          queueError instanceof Error ? queueError : new Error(String(queueError)),
          { component: 'LiveTutorPanel', phase: 'stop' },
        );
      });
    transcriptQueueRef.current = finalization;
    await finalization;
  }, [finalizeAssistantDraft, invalidateAssistantTurn, invalidateLearnerTurn, updateAssistantMessage]);

  const finishVisualStop = useCallback(() => {
    setAvatarVideoStream(null);
    setAvatarNotice(null);
    hasPlayedConnectedCueRef.current = false;
    hasSyncedInitialMuteRef.current = false;
    hasStartedRef.current = false;
    inputLevelRef.current = 0;
    outputLevelRef.current = 0;
    panelRef.current?.style.setProperty('--live-tutor-audio-scale', '1');
    setStatus('idle');
  }, [setStatus]);

  const stopAndReset = useCallback(async (): Promise<void> => {
    await stop();
    finishVisualStop();
  }, [finishVisualStop, stop]);

  const handleClose = useCallback(() => {
    playLiveVoiceCue('hangup');
    void stopAndReset();
    close();
  }, [close, stopAndReset]);

  const handleRetry = useCallback(() => {
    void (async () => {
      await stopAndReset();
      await start();
    })();
  }, [start, stopAndReset]);

  const reconfigureVoiceSession = useCallback(() => {
    if (reconfigurePromiseRef.current || !useLiveTutorStore.getState().isOpen || !hasStartedRef.current) return;
    const nextProvider = useLiveTutorStore.getState().avatarEnabled ? 'livekit_anam' : 'openai_realtime';
    const nextTutorProfile = useChatStore.getState().tutorProfile;
    if (activeProviderRef.current === nextProvider && activeTutorProfileRef.current === nextTutorProfile) return;
    logger.info('realtime.voice_configuration_change_requested', {
      component: 'LiveTutorPanel',
      fromProvider: activeProviderRef.current,
      toProvider: nextProvider,
      fromTutorProfile: activeTutorProfileRef.current,
      toTutorProfile: nextTutorProfile,
      conversationId: persistedConversationIdRef.current || conversationIdRef.current,
    });
    const pending = (async () => {
      await stopAndReset();
      if (useLiveTutorStore.getState().isOpen) await start();
    })().catch((restartError) => {
      logger.warn('realtime.voice_reconfigure_failed', {
        component: 'LiveTutorPanel',
        errorName: restartError instanceof Error ? restartError.name : 'UnknownError',
      });
      setError(labels.setupFailed);
    }).finally(() => {
      reconfigurePromiseRef.current = null;
      if (useLiveTutorStore.getState().isOpen) reconfigureVoiceSession();
    });
    reconfigurePromiseRef.current = pending;
  }, [labels.setupFailed, setError, start, stopAndReset]);

  useEffect(() => {
    if (!isOpen) return;
    void start();
    return () => {
      void stopAndReset();
    };
  }, [isOpen, start, stopAndReset]);

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
    if (isOpen) reconfigureVoiceSession();
  }, [avatarEnabled, tutorProfile, isOpen, reconfigureVoiceSession]);

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

  const isAvatarConnecting = avatarEnabled && !avatarVideoStream && !avatarNotice;
  const isAvatarVideoReady = avatarEnabled && Boolean(avatarVideoStream);
  const shouldShowConnecting = status === 'connecting' || isAvatarConnecting;
  const shouldShowStage = !shouldShowConnecting && !error && (layout === 'side-pane' || !isAvatarVideoReady);
  const useFloatingAvatarLayout = layout === 'inline' && isAvatarVideoReady;

  return (
    <section
      ref={panelRef}
      className={cx(
        styles.panel,
        layout === 'side-pane' && styles.panelSidePane,
        layout === 'inline' && hasMessages && !useFloatingAvatarLayout && styles.panelWithMessages,
        useFloatingAvatarLayout && styles.panelWithFloatingAvatar,
      )}
      aria-label={labels.title}
      data-avatar-layout={layout === 'side-pane' ? 'side-pane' : useFloatingAvatarLayout ? 'floating' : 'inline'}
    >
      <div className={cx(styles.body, layout === 'side-pane' && styles.bodySidePane)}>
        {shouldShowConnecting && !error && (
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

        {shouldShowStage && (
          <>
            {avatarNotice && <div className={styles.avatarNotice}>{avatarNotice}</div>}
            <LiveTutorAvatarStage
              avatarEnabled={avatarEnabled}
              avatarStream={layout === 'side-pane' ? avatarVideoStream : null}
              status={status}
              layout={layout === 'side-pane' ? 'side-pane' : 'inline'}
              onStreamUnhealthy={() => setAvatarVideoStream(null)}
            />
          </>
        )}

        {layout === 'inline' && isAvatarVideoReady && avatarVideoStream && !error && (
          <FloatingAvatarWindow stream={avatarVideoStream} status={status} onStreamUnhealthy={() => setAvatarVideoStream(null)} />
        )}
      </div>

      <audio ref={audioRef} autoPlay />
    </section>
  );
}

export default LiveTutorPanel;
