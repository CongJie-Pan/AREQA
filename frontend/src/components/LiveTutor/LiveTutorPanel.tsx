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
import { SpeechQueue } from '@/services/realtime/speechQueue';
import { loadVoiceMaterial, prepareVoiceAttachments } from '@/services/realtime/attachments';
import { buildVoiceAttachmentRequest, getVoiceAttachmentTask, type VoiceAttachmentTask } from '@/services/realtime/attachmentIntent';
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
  const titleRequestedConversationIdsRef = useRef(new Set<string>());
  const imageTurnIdsRef = useRef(new Set<string>());
  const pendingImageAnnouncementRef = useRef<{ text: string; epoch: number } | null>(null);
  const delegatedDeepAnswerActiveRef = useRef(false);
  const speechQueueRef = useRef<SpeechQueue | null>(null);
  const routedTurnIdsRef = useRef(new Set<string>());
  const readbackResponseIdsRef = useRef(new Set<string>());
  const speakingPracticeActiveRef = useRef(false);
  const backendReadbackActiveRef = useRef(false);
  const attachmentGenerationRef = useRef(0);
  const attachmentUploadInProgressRef = useRef(false);
  const hasVoiceMaterialRef = useRef(false);
  const awaitingUserTranscriptRef = useRef(false);
  const pendingAttachmentTaskRef = useRef<{ task: VoiceAttachmentTask; request: string } | null>(null);
  const pendingAttachmentReplyRef = useRef<{
    conversationId: string; generation: number; request: string;
  } | null>(null);
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

  const maybeGenerateVoiceTitle = useCallback((conversationId: string, firstUserText: string) => {
    if (!canPersistHistory() || !firstUserText.trim()
      || titleRequestedConversationIdsRef.current.has(conversationId)) return;
    const conversationStore = useConversationStore.getState();
    const conversation = conversationStore.conversations.find((item) => item.id === conversationId);
    if (conversation?.title !== '新對話') return;
    if (useChatStore.getState().messages.some((item) => item.conversationId === conversationId
      && item.role === 'user' && item.content.trim())) return;

    titleRequestedConversationIdsRef.current.add(conversationId);
    // Title work is independent of Realtime speech and message persistence.
    void conversationStore.generateTitle(conversationId, [{ role: 'user', content: firstUserText }]);
    logger.info('realtime.voice_title_requested', { conversationId });
  }, []);

  // Both providers already support user text with one reply. Keeping this
  // separate from silent context delivery also preserves file restoration.
  const flushAttachmentReply = useCallback(async (): Promise<boolean> => {
    const pending = pendingAttachmentReplyRef.current;
    if (!pending || userSpeakingRef.current || awaitingUserTranscriptRef.current || isCancelledRef.current) return false;
    if (pending.generation !== attachmentGenerationRef.current
      || pending.conversationId !== persistedConversationIdRef.current) {
      pendingAttachmentReplyRef.current = null;
      return false;
    }
    pendingAttachmentReplyRef.current = null;
    const task = pendingAttachmentTaskRef.current;
    try {
      const delivered = await controllerRef.current?.sendUserText?.(pending.request);
      if (!delivered) {
        if (!isCancelledRef.current && pending.generation === attachmentGenerationRef.current
          && pendingAttachmentTaskRef.current === task
          && !pendingAttachmentReplyRef.current) pendingAttachmentReplyRef.current = pending;
        logger.warn('realtime.attachment_reply_not_delivered', { conversationId: pending.conversationId });
        return false;
      }
      if (pendingAttachmentTaskRef.current === task) pendingAttachmentTaskRef.current = null;
      logger.info('realtime.attachment_reply_requested', {
        conversationId: pending.conversationId,
        generation: pending.generation,
        task: task?.task ?? 'explain',
        provider: activeProviderRef.current,
      });
      return true;
    } catch (error) {
      if (!isCancelledRef.current && pending.generation === attachmentGenerationRef.current
        && pendingAttachmentTaskRef.current === task
        && !pendingAttachmentReplyRef.current) pendingAttachmentReplyRef.current = pending;
      logger.warn('realtime.attachment_reply_failed', {
        conversationId: pending.conversationId,
        errorName: error instanceof Error ? error.name : 'UnknownError',
      });
      return false;
    }
  }, []);

  const sendVoiceMessage = useCallback(async (content: string, files: File[]) => {
    if (speechQueueRef.current) {
      speechQueueRef.current.cancel();
      speechQueueRef.current = null;
      invalidateLearnerTurn();
      backendReadbackActiveRef.current = false;
      delegatedDeepAnswerActiveRef.current = false;
      controllerRef.current?.cancelSpeech();
      void cancelCurrentStream();
    }
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
      const delivered = prepared
        ? await controller.addAttachmentContext?.(prepared.material)
        : await controller?.sendUserText?.(content);
      if (!delivered) {
        throw new Error('Voice session could not receive the message');
      }
      if (isCancelledRef.current || generation !== attachmentGenerationRef.current
        || controller !== controllerRef.current || persistedConversationIdRef.current !== conversationId) {
        throw new Error('Voice conversation changed during message delivery');
      }
      const displayContent = content.trim() || '已上傳檔案';
      const metadata = filesToAttachmentMetadata(files);
      if (content.trim()) maybeGenerateVoiceTitle(conversationId, displayContent);
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
      if (prepared) {
        hasVoiceMaterialRef.current = true;
        const typedTask = content.trim() ? getVoiceAttachmentTask(content, true) : null;
        const task: { task: VoiceAttachmentTask; request: string } | null = content.trim()
          ? { task: typedTask ?? 'explain', request: content.slice(0, 2000) }
          : pendingAttachmentTaskRef.current;
        pendingAttachmentTaskRef.current = task;
        if (task?.task !== 'wait') {
          pendingAttachmentReplyRef.current = {
            conversationId,
            generation,
            request: buildVoiceAttachmentRequest(task?.task ?? null, task?.request),
          };
          if (userSpeakingRef.current || awaitingUserTranscriptRef.current) {
            logger.info('realtime.attachment_reply_deferred', { conversationId, generation });
          } else {
            await flushAttachmentReply();
          }
        } else {
          pendingAttachmentReplyRef.current = null;
          logger.info('realtime.attachment_reply_paused', { conversationId, generation });
        }
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
  }, [addUserMessage, bumpConversationPreview, ensurePersistedConversationId, flushAttachmentReply, maybeGenerateVoiceTitle, invalidateLearnerTurn]);

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
    maybeGenerateVoiceTitle(conversationId, normalized);
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
  }, [addUserMessage, bumpConversationPreview, ensurePersistedConversationId, language, maybeGenerateVoiceTitle]);

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
      voicePlayback: options.playback ?? playbackRef.current,
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
    pendingImageAnnouncementRef.current = null;
    const sessionGeneration = ++sessionGenerationRef.current;
    const isCurrentSession = () => !isCancelledRef.current && sessionGeneration === sessionGenerationRef.current;
    const flushImageAnnouncement = (playbackStopped = false) => {
      const pending = pendingImageAnnouncementRef.current;
      if (!pending || !isCurrentSession() || pending.epoch !== speechEpochRef.current) return;
      if (userSpeakingRef.current || delegatedDeepAnswerActiveRef.current || backendReadbackActiveRef.current) return;
      if (playbackRef.current === 'playing') return;
      if (!playbackStopped && useLiveTutorStore.getState().status === 'speaking') return;
      if (controllerRef.current?.speakText(pending.text)) {
        pendingImageAnnouncementRef.current = null;
      }
    };
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
    routedTurnIdsRef.current.clear();
    readbackResponseIdsRef.current.clear();
    speechQueueRef.current?.cancel();
    speechQueueRef.current = null;
    speechEpochRef.current = 0;
    userSpeakingRef.current = false;
    speechEpochByItemRef.current.clear();
    delegatedDeepAnswerActiveRef.current = false;
    speakingPracticeActiveRef.current = false;
    backendReadbackActiveRef.current = false;
    hasVoiceMaterialRef.current = false;
    awaitingUserTranscriptRef.current = false;
    pendingAttachmentTaskRef.current = null;
    pendingAttachmentReplyRef.current = null;
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
        pendingImageAnnouncementRef.current = null;
        userSpeakingRef.current = true;
        awaitingUserTranscriptRef.current = true;
        if (itemId) speechEpochByItemRef.current.set(itemId, speechEpochRef.current);
        playbackRef.current = 'interrupted';
        speechQueueRef.current?.cancel();
        speechQueueRef.current = null;
        if (lastVoiceMessageIdRef.current) updateAssistantMessage(lastVoiceMessageIdRef.current, { voicePlayback: 'interrupted' });
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
        if (nextStatus === 'listening' || nextStatus === 'connected') flushImageAnnouncement();
        if ((nextStatus === 'connected' || nextStatus === 'listening') && !hasPlayedConnectedCueRef.current) {
          hasPlayedConnectedCueRef.current = true;
          playLiveVoiceCue('connected');
        }
      },
      onAssistantResponseStarted: (responseId, requestId) => {
        if (!isCurrentSession()) return;
        if (responseId && speechQueueRef.current?.responseStarted(responseId, requestId)) {
          readbackResponseIdsRef.current.add(responseId);
          return;
        }
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
      onAssistantResponseDone: (responseId, status) => {
        if (isCurrentSession()) speechQueueRef.current?.responseDone(responseId, status);
      },
      onPlaybackState: (state, responseId) => {
        if (!isCurrentSession()) return;
        if (speechQueueRef.current) {
          speechQueueRef.current.playback(state, responseId);
          return;
        }
        if (responseId && readbackResponseIdsRef.current.has(responseId)) return;
        if (responseId && activeAssistantResponseIdRef.current && responseId !== activeAssistantResponseIdRef.current) return;
        playbackRef.current = state === 'started' ? 'playing' : state === 'stopped' ? 'finished' : 'interrupted';
        if (state === 'stopped' || state === 'interrupted') {
          backendReadbackActiveRef.current = false;
          if (state === 'stopped') flushImageAnnouncement(true);
        }
        const playback = playbackRef.current;
        const messageId = lastVoiceMessageIdRef.current;
        if (messageId) updateAssistantMessage(messageId, { voicePlayback: playback });
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
        const normalized = normalizeVoiceTranscript(transcript, language).trim();
        // Capture intent before asynchronous persistence so a fast upload can
        // resume this spoken request rather than replace it with a default.
        if (normalized && !isSuperseded()) {
          const task = getVoiceAttachmentTask(normalized, hasVoiceMaterialRef.current
            || attachmentUploadInProgressRef.current || Boolean(pendingAttachmentTaskRef.current));
          if (task) {
            pendingAttachmentTaskRef.current = { task, request: normalized.slice(0, 2000) };
            if (task === 'wait') pendingAttachmentReplyRef.current = null;
            else if (pendingAttachmentReplyRef.current) {
              pendingAttachmentReplyRef.current.request = buildVoiceAttachmentRequest(task, normalized);
            }
            logger.info('realtime.attachment_task_selected', {
              conversationId: persistedConversationIdRef.current || conversationId,
              task,
              hasMaterial: hasVoiceMaterialRef.current,
            });
          }
        }
        if (itemId && routedTurnIdsRef.current.has(itemId)) return;
        if (itemId) routedTurnIdsRef.current.add(itemId);
        void (async () => {
          if (!isCurrentSession()) return;
          if (isSuperseded()) {
            await persistUserTranscript(normalized, itemId);
            logger.info('realtime.stale_user_turn_answer_skipped', {
              component: 'LiveTutorPanel',
              conversationId: persistedConversationIdRef.current || conversationId,
              transcriptAgeMs: Date.now() - transcriptReceivedAt,
            });
            return;
          }
          awaitingUserTranscriptRef.current = false;
          if (pendingAttachmentReplyRef.current) {
            await persistUserTranscript(normalized, itemId);
            await flushAttachmentReply();
            return;
          }
          if (!normalized) return;
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
                if (!result.completed || !isCurrentSession() || transcriptEpoch !== speechEpochRef.current) return;
                pendingImageAnnouncementRef.current = {
                  epoch: transcriptEpoch,
                  text: result.block?.visionSummary
                    ? `${language === 'en' ? 'The image is ready. ' : '圖片已完成。'}${result.block.visionSummary}`
                    : language === 'en'
                      ? 'The image is ready. You can open it in the conversation while we continue.'
                      : '圖片已完成，可以在對話中打開查看，我們可以接著討論。',
                };
                flushImageAnnouncement();
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
            if (!isCurrentSession()) return;
            if (isSuperseded()) {
              await persistUserTranscript(normalized, itemId);
              return;
            }
            const deepGeneration = invalidateLearnerTurn();
            delegatedDeepAnswerActiveRef.current = true;
            lastVoiceMessageIdRef.current = null;
            // Route before requesting any speech. A later backend result never replaces
            // an automatically started answer; one queue owns this learner turn.
            setStatus('thinking');
            let messageId: string | undefined;
            let streamed = false;
            let caption = '';
            let playbackFinished = false;
            let playbackFailed = false;
            const queue = new SpeechQueue({
              id: `${sessionGeneration}:${deepGeneration}`,
              speak: (text, requestId) => {
                if (!isCurrentSession() || !isCurrentLearnerTurn(deepGeneration)) return false;
                backendReadbackActiveRef.current = true;
                return controllerRef.current?.speakText(text, requestId) ?? false;
              },
              caption: (text) => {
                if (!isCurrentSession() || !isCurrentLearnerTurn(deepGeneration)) return;
                caption = [caption, text].filter(Boolean).join(' ');
                if (messageId) updateAssistantMessage(messageId, { voiceCaption: caption, voicePlayback: 'playing' });
              },
              complete: (failed) => {
                if (!isCurrentSession() || !isCurrentLearnerTurn(deepGeneration)) return;
                speechQueueRef.current = null;
                playbackFinished = true;
                playbackFailed = failed;
                backendReadbackActiveRef.current = false;
                if (failed) controllerRef.current?.cancelSpeech();
                if (messageId) updateAssistantMessage(messageId, {
                  voicePlayback: 'finished', voiceCaption: undefined,
                });
                logger.info('realtime.deep_answer_playback_finished', {
                  conversationId: persistedConversationId, turnId: deepGeneration, failed,
                });
              },
            });
            speechQueueRef.current?.cancel();
            speechQueueRef.current = queue;
            logger.info('realtime.deep_answer_started', {
              component: 'LiveTutorPanel', conversationId: persistedConversationId,
              provider: selectedProvider, turnId: deepGeneration,
            });
            try {
              const result = await sendMessage(normalized, persistedConversationId, [], {
                responseMode: 'voice',
                useRag: true,
                searchMode: 'auto',
                tutorProfile: selectedTutorProfile,
                speakingPractice: speakingPracticeTurn,
                onVoiceMessageStarted: (id) => {
                  if (!isCurrentSession() || !isCurrentLearnerTurn(deepGeneration)) return;
                  messageId = id;
                  lastVoiceMessageIdRef.current = id;
                },
                onVoiceContentChunk: (chunk) => {
                  if (!isCurrentSession() || !isCurrentLearnerTurn(deepGeneration)) return;
                  streamed = true;
                  queue.append(chunk);
                },
              });
              if (!isCurrentSession() || !isCurrentLearnerTurn(deepGeneration)) { queue.cancel(); return; }
              messageId = result.assistantMessageId;
              const readbackText = normalizeReadbackText(result.answerContent ?? '');
              // Persistence runs independently of playback; caption ownership was
              // established when the placeholder was created, before any content.
              void result.finalizeVoiceResponse?.(readbackText).catch((error) => logger.warn(
                'realtime.voice_finalization_failed', { errorName: error instanceof Error ? error.name : 'UnknownError' },
              ));
              if (!result.completed) {
                queue.cancel();
                speechQueueRef.current = null;
                controllerRef.current?.cancelSpeech();
                backendReadbackActiveRef.current = false;
                if (messageId) updateAssistantMessage(messageId, { voicePlayback: 'finished', voiceCaption: undefined });
              } else {
                if (messageId) updateAssistantMessage(messageId, {
                  voicePlayback: playbackFinished ? 'finished' : caption ? 'playing' : 'waiting',
                  voiceCaption: playbackFinished ? undefined : caption,
                });
                if (!streamed) queue.append(readbackText);
                queue.finish();
                if (playbackFailed && messageId) updateAssistantMessage(messageId, { voicePlayback: 'finished', voiceCaption: undefined });
              }
              logger.info('realtime.deep_answer_completed', {
                component: 'LiveTutorPanel',
                conversationId: persistedConversationId,
                stale: !isCurrentLearnerTurn(deepGeneration),
                completed: result.completed,
                answerChars: result.answerContent?.length ?? 0,
              });
            } catch (error) {
              queue.cancel();
              if (speechQueueRef.current === queue) speechQueueRef.current = null;
              if (isCurrentSession() && isCurrentLearnerTurn(deepGeneration)) {
                if (messageId) updateAssistantMessage(messageId, { voicePlayback: 'finished', voiceCaption: undefined });
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
          if (isCurrentSession() && !isSuperseded()) {
            controllerRef.current?.requestResponse?.();
            logger.info('realtime.voice_reply_requested', {
              component: 'LiveTutorPanel',
              conversationId: persistedConversationIdRef.current || conversationId,
              transcriptToReplyMs: Date.now() - transcriptReceivedAt,
            });
          }
        })().catch((error) => logger.warn('realtime.voice_routing_failed', {
          conversationId: persistedConversationIdRef.current || conversationId,
          errorName: error instanceof Error ? error.name : 'UnknownError',
        }));
      },
      onAssistantTranscriptDelta: (delta, responseId) => {
        if (!isCurrentSession() || delegatedDeepAnswerActiveRef.current || backendReadbackActiveRef.current || !delta
          || (responseId && readbackResponseIdsRef.current.has(responseId))) return;
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
        if (!isCurrentSession() || delegatedDeepAnswerActiveRef.current || backendReadbackActiveRef.current
          || (responseId && readbackResponseIdsRef.current.has(responseId))) return;
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
    void loadVoiceMaterial(conversationId).then(async (material) => {
      if (!material || !isCurrentSession() || attachmentGeneration !== attachmentGenerationRef.current) return;
      const delivered = await controller.addAttachmentContext?.(material);
      if (delivered && isCurrentSession() && attachmentGeneration === attachmentGenerationRef.current) {
        hasVoiceMaterialRef.current = true;
      }
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
    flushAttachmentReply,
  ]);

  const stop = useCallback(async (): Promise<void> => {
    sessionGenerationRef.current += 1;
    attachmentGenerationRef.current += 1;
    isCancelledRef.current = true;
    pendingImageAnnouncementRef.current = null;
    pendingAttachmentReplyRef.current = null;
    pendingAttachmentTaskRef.current = null;
    hasVoiceMaterialRef.current = false;
    awaitingUserTranscriptRef.current = false;
    userSpeakingRef.current = false;
    speechEpochByItemRef.current.clear();
    delegatedDeepAnswerActiveRef.current = false;
    backendReadbackActiveRef.current = false;
    playbackRef.current = 'interrupted';
    speechQueueRef.current?.cancel();
    speechQueueRef.current = null;
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
          updateAssistantMessage(lastVoiceMessageId, { isStreaming: false });
        }
        for (const id of pendingUserTurnIds) {
          useChatStore.getState().removeMessage(id);
        }
        assistantMessageIdRef.current = null;
        assistantTranscriptRef.current = '';
        lastVoiceMessageIdRef.current = null;
        userTurnIdsRef.current.clear();
    routedTurnIdsRef.current.clear();
    readbackResponseIdsRef.current.clear();
    speechQueueRef.current?.cancel();
    speechQueueRef.current = null;
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
