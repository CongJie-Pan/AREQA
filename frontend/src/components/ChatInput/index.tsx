'use client';

/**
 * ChatInput Component
 * Text input for sending messages with validation
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  ArrowUp,
  AudioLines,
  BookOpen,
  Check,
  CornerDownRight,
  FileText,
  FileImage,
  ImagePlus,
  Globe2,
  Mic,
  MicOff,
  Plus,
  Square,
  Upload,
  Video,
  VideoOff,
  X,
} from 'lucide-react';
import { Dropdown, message, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { useChatStore } from '@/store/chat';
import { useStyles } from './styles';
import { normalizeDisplayMathBlocks, rehypeMathSource } from '@/utils/markdownMath';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { transcribeSpeech } from '@/services/speech/transcription';
import { normalizeVoiceTranscript } from '@/services/realtime/language';

/** Maximum allowed message length */
const MAX_MESSAGE_LENGTH = 4000;
/** Maximum number of files that can be staged in one outgoing message. */
const MAX_ATTACHMENT_COUNT = 5;
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const DICTATION_WAVE_BAR_COUNT = 34;
const IDLE_DICTATION_WAVE_LEVEL = 0.1;
const EXPANDED_COMPOSER_MIN_SCROLL_HEIGHT = 34;
const EXPANDED_COMPOSER_MIN_CHARS = 96;
const SUPPORTED_ATTACHMENT_TYPES = new Set([
  'image/png', 'image/jpeg', 'image/webp', 'image/gif',
  'application/pdf', 'text/plain', 'text/markdown',
]);
const GENERIC_TEXT_UPLOAD_TYPES = new Set(['', 'application/octet-stream', 'text/plain', 'text/markdown']);
const PASTED_IMAGE_EXTENSION_BY_TYPE: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
  'image/gif': 'gif',
};

type AttachmentValidationKey =
  | 'maxAttachments'
  | 'unsupportedAttachment'
  | 'emptyAttachment'
  | 'attachmentTooLarge'
  | 'attachmentsTooLarge';

interface AttachmentPreview {
  file: File;
  objectUrl: string | null;
}

/**
 * Validates the complete staged attachment set before state changes.
 *
 * Args:
 *   currentAttachments: Files already staged in the composer.
 *   incomingAttachments: Files from picker, paste, or drag-and-drop.
 *
 * Returns:
 *   A translation key for the first validation failure, or null when accepted.
 *
 * Side effects:
 *   None.
 */
function validateAttachmentCandidates(currentAttachments: File[], incomingAttachments: File[]): AttachmentValidationKey | null {
  const candidates = [...currentAttachments, ...incomingAttachments];
  if (candidates.length > MAX_ATTACHMENT_COUNT) {
    return 'maxAttachments';
  }

  let totalSize = 0;
  for (const attachment of candidates) {
    if (!isSupportedAttachment(attachment)) {
      return 'unsupportedAttachment';
    }
    if (attachment.size === 0) {
      return 'emptyAttachment';
    }
    if (attachment.size > MAX_ATTACHMENT_BYTES) {
      return 'attachmentTooLarge';
    }
    totalSize += attachment.size;
  }

  return totalSize > MAX_TOTAL_ATTACHMENT_BYTES ? 'attachmentsTooLarge' : null;
}

function isSupportedAttachment(attachment: File): boolean {
  if (SUPPORTED_ATTACHMENT_TYPES.has(attachment.type)) return true;
  const extension = attachment.name.split('.').pop()?.toLowerCase() ?? '';
  return ['txt', 'md'].includes(extension) && GENERIC_TEXT_UPLOAD_TYPES.has(attachment.type);
}

/**
 * Checks whether a drag event carries files rather than selected text or links.
 *
 * Args:
 *   event: Native window drag event.
 *
 * Returns:
 *   True when the browser reports a file payload.
 *
 * Side effects:
 *   None.
 */
function isFileDrag(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files');
}

/**
 * Converts browser FileList values into arrays for shared validation.
 *
 * Args:
 *   files: FileList, array, null, or undefined from a browser input source.
 *
 * Returns:
 *   A plain File array.
 *
 * Side effects:
 *   None.
 */
function fileListToArray(files: FileList | File[] | null | undefined): File[] {
  return Array.from(files ?? []);
}

/**
 * Gives clipboard images deterministic File metadata before upload.
 *
 * Args:
 *   file: Browser-provided clipboard image file.
 *
 * Returns:
 *   A new File with a timestamped name and preserved MIME type.
 *
 * Side effects:
 *   Reads the current time for the generated filename.
 */
function createPastedImageFile(file: File): File {
  const extension = PASTED_IMAGE_EXTENSION_BY_TYPE[file.type] ?? 'png';
  return new File(
    [file],
    `pasted-image-${new Date().toISOString().replace(/[:.]/g, '-')}.${extension}`,
    { type: file.type, lastModified: Date.now() },
  );
}

/**
 * Extracts image files from clipboard data while ignoring pasted text.
 *
 * Args:
 *   items: Clipboard items from a paste event.
 *
 * Returns:
 *   Timestamped image files that can enter the regular attachment pipeline.
 *
 * Side effects:
 *   Reads clipboard item file handles supplied by the browser event.
 */
function clipboardImagesToFiles(items: DataTransferItemList | undefined): File[] {
  return Array.from(items ?? [])
    .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null)
    .map(createPastedImageFile);
}

/**
 * Formats byte counts for compact attachment preview cards.
 *
 * Args:
 *   bytes: File size in bytes.
 *
 * Returns:
 *   Human-readable B, KB, or MB text.
 *
 * Side effects:
 *   None.
 */
function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Monitors a microphone stream and maps recent audio energy to waveform bars.
 *
 * Args:
 *   stream: Browser microphone stream captured for composer dictation.
 *   onLevels: Receives normalized bar levels in the range [0, 1].
 *
 * Returns:
 *   Cleanup callback that stops animation frames and closes the audio context.
 *
 * Side effects:
 *   Creates a short-lived Web Audio analyser. It does not record, persist, or
 *   log raw audio; the caller owns MediaRecorder capture separately.
 */
function startDictationLevelMonitor(
  stream: MediaStream,
  onLevels: (levels: number[]) => void,
): () => void {
  if (typeof window === 'undefined' || !window.AudioContext) {
    return () => undefined;
  }

  let audioContext: AudioContext;
  let analyser: AnalyserNode;
  let source: MediaStreamAudioSourceNode;
  try {
    audioContext = new window.AudioContext();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.82;
    source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    if (audioContext.state === 'suspended') {
      void audioContext.resume().catch(() => undefined);
    }
  } catch {
    return () => undefined;
  }

  const samples = new Uint8Array(analyser.frequencyBinCount);
  let animationFrameId = 0;
  let closed = false;
  let smoothedLevel = IDLE_DICTATION_WAVE_LEVEL;
  let frame = 0;

  const tick = () => {
    if (closed) return;
    analyser.getByteFrequencyData(samples);
    const sum = samples.reduce((total, sample) => total + sample, 0);
    const rawLevel = Math.min(1, Math.max(0, (sum / Math.max(samples.length, 1) - 5) / 92));
    smoothedLevel += (rawLevel - smoothedLevel) * (rawLevel > smoothedLevel ? 0.28 : 0.12);
    frame += 1;
    onLevels(Array.from({ length: DICTATION_WAVE_BAR_COUNT }, (_, index) => {
      const centerDistance = Math.abs(index - (DICTATION_WAVE_BAR_COUNT - 1) / 2) / (DICTATION_WAVE_BAR_COUNT / 2);
      const centerWeight = Math.max(0.16, 1 - centerDistance ** 1.9);
      const breathing = 0.04 * Math.sin(frame * 0.09 + index * 0.72);
      const level = IDLE_DICTATION_WAVE_LEVEL + smoothedLevel * centerWeight + breathing;
      return Math.min(0.84, Math.max(IDLE_DICTATION_WAVE_LEVEL, level));
    }));
    animationFrameId = window.requestAnimationFrame(tick);
  };

  animationFrameId = window.requestAnimationFrame(tick);

  return () => {
    closed = true;
    if (animationFrameId) window.cancelAnimationFrame(animationFrameId);
    source.disconnect();
    analyser.disconnect();
    onLevels(Array.from({ length: DICTATION_WAVE_BAR_COUNT }, () => IDLE_DICTATION_WAVE_LEVEL));
    void audioContext.close().catch(() => undefined);
  };
}

export interface ChatInputProps {
  /** Callback when message is sent */
  onSend: (message: string, attachments?: File[], options?: { createImage?: boolean }) =>
    | void
    | { completed: boolean; cancelled?: boolean }
    | Promise<void | { completed: boolean; cancelled?: boolean }>;
  /** Whether input is disabled */
  disabled?: boolean;
  /** Placeholder text */
  placeholder?: string;
  /** Class name for styling */
  className?: string;
  /** Maximum message length (default: 4000) */
  maxLength?: number;
  /** Whether AI is currently streaming response */
  isStreaming?: boolean;
  /** Whether an image job is preparing or generating independently of streaming. */
  isGeneratingImage?: boolean;
  /** Callback when stop button is clicked */
  onStop?: () => void;
  /** Callback when the live voice tutor button is clicked. */
  onOpenLiveTutor?: () => void;
  /** Whether the composer is controlling an active live voice session. */
  isLiveVoiceActive?: boolean;
  /** Whether the active live voice microphone is muted. */
  isLiveVoiceMuted?: boolean;
  /** Whether avatar video is preferred for the active live voice session. */
  isLiveVoiceAvatarEnabled?: boolean;
  /** Callback that toggles microphone capture for the active voice session. */
  onToggleLiveVoiceMute?: () => void;
  /** Callback that toggles avatar video rendering for the active voice session. */
  onToggleLiveVoiceAvatar?: () => void;
  /** Callback that ends the active live voice session. */
  onCloseLiveVoice?: () => void;
}

const LIVE_VOICE_LABELS = {
  'zh-TW': {
    open: '開啟即時語音',
    mute: '靜音',
    unmute: '取消靜音',
    avatarOn: '開啟虛擬角色',
    avatarOff: '關閉虛擬角色',
    close: '結束語音',
  },
  'zh-CN': {
    open: '开启即时语音',
    mute: '静音',
    unmute: '取消静音',
    avatarOn: '开启虚拟角色',
    avatarOff: '关闭虚拟角色',
    close: '结束语音',
  },
  en: {
    open: 'Start live voice',
    mute: 'Mute',
    unmute: 'Unmute',
    avatarOn: 'Show avatar',
    avatarOff: 'Hide avatar',
    close: 'End voice',
  },
} as const;

const DICTATION_LABELS = {
  'zh-TW': {
    start: '語音輸入',
    cancel: '取消語音輸入',
    confirm: '確認語音輸入',
    unavailable: '此瀏覽器不支援語音輸入。',
    failed: '語音轉文字失敗，請稍後再試。',
  },
  'zh-CN': {
    start: '语音输入',
    cancel: '取消语音输入',
    confirm: '确认语音输入',
    unavailable: '此浏览器不支持语音输入。',
    failed: '语音转文字失败，请稍后再试。',
  },
  en: {
    start: 'Voice dictation',
    cancel: 'Cancel dictation',
    confirm: 'Confirm dictation',
    unavailable: 'Voice dictation is not supported in this browser.',
    failed: 'Speech transcription failed. Please try again.',
  },
} as const;

const WEB_SEARCH_LABELS = {
  'zh-TW': {
    enable: '開啟網路搜尋',
    disable: '關閉網路搜尋',
  },
  'zh-CN': {
    enable: '开启网络搜索',
    disable: '关闭网络搜索',
  },
  en: {
    enable: 'Enable web search',
    disable: 'Disable web search',
  },
} as const;

const ADD_MENU_LABELS = {
  'zh-TW': {
    open: '新增',
    upload: '上傳檔案',
    createImage: 'Create Image',
    englishTutor: 'English Tutor',
    englishTutorDescription: '英文口說、閱讀、寫作與文學分析',
  },
  'zh-CN': {
    open: '新增',
    upload: '上传文件',
    createImage: 'Create Image',
    englishTutor: 'English Tutor',
    englishTutorDescription: '英文口语、阅读、写作与文学分析',
  },
  en: {
    open: 'Add',
    upload: 'Upload file',
    createImage: 'Create Image',
    englishTutor: 'English Tutor',
    englishTutorDescription: 'Speaking, reading, writing, and literary analysis',
  },
} as const;

/**
 * ChatInput provides text input for sending messages
 * Supports Enter to send, Shift+Enter for new line
 */
export function ChatInput({
  onSend,
  disabled = false,
  placeholder,
  className,
  maxLength = MAX_MESSAGE_LENGTH,
  isStreaming = false,
  isGeneratingImage = false,
  onStop,
  onOpenLiveTutor,
  isLiveVoiceActive = false,
  isLiveVoiceMuted = false,
  isLiveVoiceAvatarEnabled = false,
  onToggleLiveVoiceMute,
  onToggleLiveVoiceAvatar,
  onCloseLiveVoice,
}: ChatInputProps) {
  const { styles, cx } = useStyles();
  const { t, language } = useUserPreferences();
  const liveVoiceLabels = LIVE_VOICE_LABELS[language];
  const dictationLabels = DICTATION_LABELS[language];
  const webSearchLabels = WEB_SEARCH_LABELS[language];
  const addMenuLabels = ADD_MENU_LABELS[language];
  const [value, setValue] = useState('');
  const [createImage, setCreateImage] = useState(false);
  const composerVersionRef = useRef(0);
  const [attachmentPreviews, setAttachmentPreviews] = useState<AttachmentPreview[]>([]);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const [isTextareaMultiline, setIsTextareaMultiline] = useState(false);
  const [dictationState, setDictationState] = useState<'idle' | 'recording' | 'transcribing'>('idle');
  const [dictationLevels, setDictationLevels] = useState<number[]>(
    () => Array.from({ length: DICTATION_WAVE_BAR_COUNT }, () => IDLE_DICTATION_WAVE_LEVEL),
  );
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const internalDragRef = useRef(false);
  const attachmentPreviewsRef = useRef<AttachmentPreview[]>([]);
  const dictationChunksRef = useRef<Blob[]>([]);
  const dictationStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const shouldTranscribeDictationRef = useRef(false);
  const stopDictationLevelMonitorRef = useRef<(() => void) | null>(null);
  
  // Connect to global state for mode togglers
  const quotedText = useChatStore((state) => state.quotedText);
  const setQuotedText = useChatStore((state) => state.setQuotedText);
  const useWebSearch = useChatStore((state) => state.useWebSearch);
  const toggleWebSearch = useChatStore((state) => state.toggleWebSearch);
  const tutorProfile = useChatStore((state) => state.tutorProfile);
  const setTutorProfile = useChatStore((state) => state.setTutorProfile);

  const isOverLimit = value.length > maxLength;
  const hasMath = /(?:\$\$?[\s\S]+?\$\$?|\\\(|\\\[)/.test(value);
  const shouldUseExpandedShape = attachmentPreviews.length > 0
    || Boolean(quotedText)
    || tutorProfile === 'english'
    || isTextareaMultiline
    || value.includes('\n')
    || value.length > EXPANDED_COMPOSER_MIN_CHARS;

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
      setIsTextareaMultiline(textarea.scrollHeight > EXPANDED_COMPOSER_MIN_SCROLL_HEIGHT);
    }
  }, [value]);

  // Focus textarea when quotedText changes
  useEffect(() => {
    if (quotedText && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [quotedText]);

  useEffect(() => {
    attachmentPreviewsRef.current = attachmentPreviews;
  }, [attachmentPreviews]);

  useEffect(() => () => {
    for (const preview of attachmentPreviewsRef.current) {
      if (preview.objectUrl) URL.revokeObjectURL(preview.objectUrl);
    }
    mediaRecorderRef.current = null;
    stopDictationLevelMonitorRef.current?.();
    stopDictationLevelMonitorRef.current = null;
    dictationStreamRef.current?.getTracks().forEach((track) => track.stop());
    dictationStreamRef.current = null;
  }, []);

  const reportAttachmentError = useCallback((errorKey: AttachmentValidationKey) => {
    if (errorKey === 'maxAttachments') {
      message.error(t(errorKey, { count: MAX_ATTACHMENT_COUNT }));
      return;
    }
    message.error(t(errorKey));
  }, [t]);

  const addAttachments = useCallback((incomingAttachments: File[]) => {
    if (incomingAttachments.length === 0 || disabled) return;

    const currentFiles = attachmentPreviews.map((preview) => preview.file);
    const validationError = validateAttachmentCandidates(currentFiles, incomingAttachments);
    if (validationError) {
      reportAttachmentError(validationError);
      return;
    }

    setAttachmentPreviews((current) => [
      ...current,
      ...incomingAttachments.map((file) => ({
        file,
        objectUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
      })),
    ]);
  }, [attachmentPreviews, disabled, reportAttachmentError]);

  useEffect(() => {
    const resetDragState = () => {
      internalDragRef.current = false;
      dragDepthRef.current = 0;
      setIsDraggingFiles(false);
    };

    const handleDocumentDragStart = () => {
      internalDragRef.current = true;
      dragDepthRef.current = 0;
      setIsDraggingFiles(false);
    };

    const handleWindowDragEnter = (event: DragEvent) => {
      if (internalDragRef.current) return;
      if (!isFileDrag(event)) return;
      event.preventDefault();
      dragDepthRef.current += 1;
      if (!disabled) setIsDraggingFiles(true);
    };

    const handleWindowDragOver = (event: DragEvent) => {
      if (internalDragRef.current) return;
      if (!isFileDrag(event)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = disabled ? 'none' : 'copy';
    };

    const handleWindowDragLeave = (event: DragEvent) => {
      if (internalDragRef.current) return;
      if (!isFileDrag(event)) return;
      event.preventDefault();
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) setIsDraggingFiles(false);
    };

    const handleWindowDrop = (event: DragEvent) => {
      if (internalDragRef.current) {
        resetDragState();
        return;
      }
      if (!isFileDrag(event)) return;
      event.preventDefault();
      dragDepthRef.current = 0;
      setIsDraggingFiles(false);
      addAttachments(fileListToArray(event.dataTransfer?.files));
    };

    document.addEventListener('dragstart', handleDocumentDragStart, true);
    document.addEventListener('dragend', resetDragState, true);
    window.addEventListener('dragenter', handleWindowDragEnter);
    window.addEventListener('dragover', handleWindowDragOver);
    window.addEventListener('dragleave', handleWindowDragLeave);
    window.addEventListener('drop', handleWindowDrop);

    return () => {
      document.removeEventListener('dragstart', handleDocumentDragStart, true);
      document.removeEventListener('dragend', resetDragState, true);
      window.removeEventListener('dragenter', handleWindowDragEnter);
      window.removeEventListener('dragover', handleWindowDragOver);
      window.removeEventListener('dragleave', handleWindowDragLeave);
      window.removeEventListener('drop', handleWindowDrop);
    };
  }, [addAttachments, disabled]);

  const handleSend = useCallback(async () => {
    const trimmedValue = value.trim();
    const composerVersionAtSend = composerVersionRef.current;
    const sendingAsImage = createImage;
    const previewsToSend = attachmentPreviews;
    const quotedTextToSend = quotedText;

    // Validation checks
    if (!trimmedValue && !quotedTextToSend && previewsToSend.length === 0) {
      return;
    }

    if (disabled || isGeneratingImage) return;

    // Check message length
    if (trimmedValue.length > maxLength) {
      message.error(t('messageTooLong', { maxLength }));
      return;
    }

    // Construct final message with quote if exists
    let finalMessage = trimmedValue;
    if (quotedTextToSend) {
      const formattedQuote = quotedTextToSend
        .split('\n')
        .map(line => (line.startsWith('>') ? line : `> ${line}`))
        .join('\n');
      const quotePrompt = trimmedValue || t('quotedTextDefaultPrompt');
      finalMessage = `${formattedQuote}\n\n${quotePrompt}`;
    }

    setValue('');
    if (sendingAsImage) setCreateImage(false);
    setIsTextareaMultiline(false);
    setAttachmentPreviews([]);
    setQuotedText(null);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    const restoreDraft = () => {
      setValue((currentValue) => (currentValue === '' ? value : currentValue));
      setAttachmentPreviews((currentPreviews) => (
        currentPreviews.length === 0 ? previewsToSend : currentPreviews
      ));
      if (quotedTextToSend) {
        setQuotedText(quotedTextToSend);
      }
    };

    try {
      const filesToSend = previewsToSend.map((preview) => preview.file);
      const result = createImage
        ? await onSend(finalMessage, filesToSend, { createImage: true })
        : filesToSend.length > 0
          ? await onSend(finalMessage, filesToSend)
          : await onSend(finalMessage);

      if (result && 'completed' in result && !result.completed && !result.cancelled) {
        restoreDraft();
        if (sendingAsImage && composerVersionRef.current === composerVersionAtSend) setCreateImage(true);
        return;
      }

      for (const preview of previewsToSend) {
        if (preview.objectUrl) URL.revokeObjectURL(preview.objectUrl);
      }
    } catch {
      // Preserve text and attachments so the user can retry the request.
      restoreDraft();
      if (sendingAsImage && composerVersionRef.current === composerVersionAtSend) setCreateImage(true);
      return;
    }
  }, [value, attachmentPreviews, createImage, disabled, isGeneratingImage, onSend, maxLength, quotedText, setQuotedText, t]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Ignore if user is composing text (e.g. using IME for Chinese)
      if (e.nativeEvent.isComposing) return;

      // Enter to send, Shift+Enter for new line
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      composerVersionRef.current += 1;
      setValue(e.target.value);
    },
    []
  );

  const handleAttachmentChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = fileListToArray(event.target.files);
    event.target.value = '';
    addAttachments(selected);
  }, [addAttachments]);

  const handlePaste = useCallback((event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const imageFiles = clipboardImagesToFiles(event.clipboardData?.items);
    if (imageFiles.length === 0) return;
    event.preventDefault();
    addAttachments(imageFiles);
  }, [addAttachments]);

  const removeAttachment = useCallback((target: AttachmentPreview) => {
    if (target.objectUrl) URL.revokeObjectURL(target.objectUrl);
    setAttachmentPreviews((current) => current.filter((preview) => preview !== target));
  }, []);

  const canSend = (value.trim().length > 0 || attachmentPreviews.length > 0) && !disabled && !isGeneratingImage && !isOverLimit;
  const showStop = onStop && (isGeneratingImage || (isStreaming && !(isLiveVoiceActive && onCloseLiveVoice)));
  const hasComposerContent = value.trim().length > 0 || attachmentPreviews.length > 0 || Boolean(quotedText);
  const addMenuItems: MenuProps['items'] = [
    {
      key: 'create-image',
      icon: <ImagePlus size={15} />,
      label: addMenuLabels.createImage,
    },
    {
      key: 'upload',
      icon: <Upload size={15} />,
      label: addMenuLabels.upload,
    },
    {
      key: 'english',
      icon: <BookOpen size={15} />,
      label: (
        <span className={styles.addMenuTutorItem}>
          <span>{addMenuLabels.englishTutor}</span>
          <small>{addMenuLabels.englishTutorDescription}</small>
        </span>
      ),
    },
  ];

  const handleAddMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (disabled || dictationState !== 'idle') return;
    if (key === 'create-image') {
      setCreateImage((current) => !current);
      textareaRef.current?.focus();
      return;
    }
    if (key === 'upload') {
      fileInputRef.current?.click();
      return;
    }
    if (key === 'english') {
      setTutorProfile(tutorProfile === 'english' ? 'general' : 'english');
    }
  };

  const stopDictationTracks = useCallback(() => {
    stopDictationLevelMonitorRef.current?.();
    stopDictationLevelMonitorRef.current = null;
    setDictationLevels(Array.from({ length: DICTATION_WAVE_BAR_COUNT }, () => IDLE_DICTATION_WAVE_LEVEL));
    dictationStreamRef.current?.getTracks().forEach((track) => track.stop());
    dictationStreamRef.current = null;
  }, []);

  const startDictation = useCallback(async () => {
    if (disabled || dictationState !== 'idle') return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      message.error(dictationLabels.unavailable);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const options = MediaRecorder.isTypeSupported?.('audio/webm;codecs=opus')
        ? { mimeType: 'audio/webm;codecs=opus' }
        : undefined;
      const recorder = new MediaRecorder(stream, options);
      dictationChunksRef.current = [];
      dictationStreamRef.current = stream;
      stopDictationLevelMonitorRef.current = startDictationLevelMonitor(stream, setDictationLevels);
      mediaRecorderRef.current = recorder;
      shouldTranscribeDictationRef.current = false;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) dictationChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const shouldTranscribe = shouldTranscribeDictationRef.current;
        const chunks = dictationChunksRef.current;
        const mimeType = recorder.mimeType || 'audio/webm';
        mediaRecorderRef.current = null;
        shouldTranscribeDictationRef.current = false;
        stopDictationTracks();
        if (!shouldTranscribe) {
          setDictationState('idle');
          return;
        }
        setDictationState('transcribing');
        void transcribeSpeech(new Blob(chunks, { type: mimeType }), language)
          .then((transcript) => {
            const normalizedTranscript = normalizeVoiceTranscript(transcript, language).trim();
            if (!normalizedTranscript) return;
            setValue((current) => (current.trim()
              ? `${current.trimEnd()} ${normalizedTranscript}`
              : normalizedTranscript));
            requestAnimationFrame(() => textareaRef.current?.focus());
          })
          .catch(() => {
            message.error(dictationLabels.failed);
          })
          .finally(() => {
            setDictationState('idle');
          });
      };
      recorder.start();
      setDictationState('recording');
    } catch {
      stopDictationTracks();
      mediaRecorderRef.current = null;
      setDictationState('idle');
      message.error(dictationLabels.failed);
    }
  }, [dictationLabels.failed, dictationLabels.unavailable, dictationState, disabled, language, stopDictationTracks]);

  const stopDictation = useCallback((shouldTranscribe: boolean) => {
    const recorder = mediaRecorderRef.current;
    shouldTranscribeDictationRef.current = shouldTranscribe;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
      return;
    }
    shouldTranscribeDictationRef.current = false;
    stopDictationTracks();
    setDictationState('idle');
  }, [stopDictationTracks]);

  return (
    <>
    {isDraggingFiles && (
      <div className={styles.dropOverlay} role="status" aria-live="polite">
        <div className={styles.dropOverlayPanel}>
          <div className={styles.dropOverlayTitle}>{t('dropFilesTitle')}</div>
          <div className={styles.dropOverlaySubtitle}>{t('dropFilesSubtitle')}</div>
        </div>
      </div>
    )}
    <div
      className={cx(
        'areqa-chat-input-shell',
        attachmentPreviews.length > 0 && 'areqa-chat-input-shell-has-attachments',
        shouldUseExpandedShape && 'areqa-chat-input-shell-expanded',
        styles.container,
        shouldUseExpandedShape && styles.containerExpanded,
        attachmentPreviews.length > 0 && styles.containerWithAttachments,
        className,
      )}
    >
      {/* Quote Preview */}
      {quotedText && (
        <div className={cx('areqa-chat-input-quote-preview', styles.quotePreview)}>
          <CornerDownRight size={14} className={cx('areqa-chat-input-quote-arrow', styles.quoteArrow)} />
          <div className={cx('areqa-chat-input-quote-content', styles.quoteContent)}>{quotedText}</div>
          <button
            className={cx('areqa-chat-input-quote-close', styles.quoteClose)}
            onClick={() => setQuotedText(null)}
            aria-label={t('cancelQuote')}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {attachmentPreviews.length > 0 && (
        <div className={cx('areqa-chat-input-attachment-list', styles.attachmentList)} aria-label={t('pendingAttachments')}>
          {attachmentPreviews.map((preview) => {
            const { file: attachment, objectUrl } = preview;
            const isImagePreview = Boolean(objectUrl && attachment.type.startsWith('image/'));
            const AttachmentIcon = attachment.type.startsWith('image/') ? FileImage : FileText;
            if (isImagePreview) {
              return (
                <div
                  className={cx('areqa-chat-input-image-attachment-chip', styles.imageAttachmentChip)}
                  key={`${attachment.name}-${attachment.lastModified}`}
                  title={attachment.name}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={objectUrl ?? ''}
                    alt={t('attachmentImagePreview')}
                    className={cx('areqa-chat-input-attachment-thumbnail', styles.attachmentThumbnail)}
                  />
                  <button
                    className={cx('areqa-chat-input-image-attachment-remove', styles.imageAttachmentRemove)}
                    type="button"
                    onClick={() => removeAttachment(preview)}
                    aria-label={`${t('delete')} ${attachment.name}`}
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            }

            return (
            <div className={cx('areqa-chat-input-attachment-chip', styles.attachmentChip)} key={`${attachment.name}-${attachment.lastModified}`}>
              <span className={cx('areqa-chat-input-attachment-icon', styles.attachmentIconFrame)} aria-hidden="true">
                <AttachmentIcon size={20} className={styles.attachmentFileIcon} />
              </span>
              <span className={cx('areqa-chat-input-attachment-details', styles.attachmentDetails)} title={attachment.name}>
                <span>{attachment.name}</span>
                <small>{formatAttachmentSize(attachment.size)}</small>
              </span>
              <button type="button" onClick={() => removeAttachment(preview)} aria-label={`${t('delete')} ${attachment.name}`}>
                <X size={13} />
              </button>
            </div>
          );
          })}
        </div>
      )}

      {createImage && (
        <div className={styles.tutorProfileBar}>
          <span className={styles.tutorProfileChip}>
            <ImagePlus size={14} /> {addMenuLabels.createImage}
            <button type="button" onClick={() => setCreateImage(false)} aria-label="Cancel Create Image"><X size={14} /></button>
          </span>
        </div>
      )}
      {tutorProfile === 'english' && (
        <div className={styles.tutorProfileBar}>
          <span className={styles.tutorProfileChip}>
            <BookOpen size={14} />
            <span>{addMenuLabels.englishTutor}</span>
            <button
              type="button"
              onClick={() => setTutorProfile('general')}
              aria-label={`${t('delete')} ${addMenuLabels.englishTutor}`}
            >
              <X size={12} />
            </button>
          </span>
        </div>
      )}

      <div
        className={cx(
          'areqa-chat-input-row',
          styles.inputRow,
          dictationState !== 'idle' && styles.inputRowRecording,
        )}
        role="group"
        aria-label={t('messageInputRow')}
      >
        <Dropdown
          menu={{
            items: addMenuItems,
            onClick: handleAddMenuClick,
            selectable: true,
            selectedKeys: [
              ...(tutorProfile === 'english' ? ['english'] : []),
              ...(createImage ? ['create-image'] : []),
            ],
          }}
          trigger={['click']}
          disabled={disabled || dictationState !== 'idle'}
          placement="topLeft"
        >
          <Tooltip title={addMenuLabels.open} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button
              type="button"
              className={cx(
                'areqa-chat-input-attachment-button',
                styles.attachmentButton,
                tutorProfile === 'english' && styles.attachmentButtonActive,
                dictationState !== 'idle' && styles.recordingInactiveControl,
              )}
              disabled={disabled || dictationState !== 'idle'}
              aria-label={addMenuLabels.open}
              aria-haspopup="menu"
              aria-pressed={tutorProfile === 'english'}
            >
              <Plus size={18} />
            </button>
          </Tooltip>
        </Dropdown>
        {dictationState !== 'idle' ? (
          <>
            <div className={styles.dictationWave} aria-hidden>
              {dictationLevels.map((level, index) => (
                <span key={index} style={{ '--wave-level': level.toFixed(3) } as React.CSSProperties} />
              ))}
            </div>
            <button
              type="button"
              className={cx(styles.iconButton, styles.cancelDictationButton)}
              onClick={() => stopDictation(false)}
              aria-label={dictationLabels.cancel}
              disabled={dictationState === 'transcribing'}
            >
              <X size={21} />
            </button>
            <button
              type="button"
              className={cx(styles.iconButton, styles.confirmDictationButton)}
              onClick={() => stopDictation(true)}
              aria-label={dictationLabels.confirm}
              disabled={dictationState === 'transcribing'}
            >
              <Check size={22} />
            </button>
          </>
        ) : (
          <>
            <textarea
              ref={textareaRef}
              className={cx('areqa-chat-input-textarea', styles.textarea)}
              value={value}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={placeholder ?? t('askPlaceholder')}
              disabled={disabled}
              rows={1}
              maxLength={maxLength + 100}
              aria-label={t('messageTextarea')}
            />
            <Tooltip title={useWebSearch ? webSearchLabels.disable : webSearchLabels.enable} color="#262626" styles={{ container: { color: '#ffffff' } }}>
              <button
                type="button"
                className={cx(
                  'areqa-chat-input-web-search-button',
                  styles.iconButton,
                  styles.webSearchButton,
                  useWebSearch && styles.webSearchButtonActive,
                )}
                onClick={toggleWebSearch}
                disabled={disabled}
                aria-label={useWebSearch ? webSearchLabels.disable : webSearchLabels.enable}
                aria-pressed={useWebSearch}
              >
                <Globe2 size={19} />
              </button>
            </Tooltip>
            <Tooltip title={dictationLabels.start} color="#262626" styles={{ container: { color: '#ffffff' } }}>
              <button
                type="button"
                className={cx('areqa-chat-input-dictation-button', styles.iconButton, styles.dictationButton)}
                onClick={startDictation}
                disabled={disabled || isLiveVoiceActive}
                aria-label={dictationLabels.start}
              >
                <Mic size={20} />
              </button>
            </Tooltip>
          </>
        )}
        {dictationState !== 'idle' ? null : isLiveVoiceActive && onToggleLiveVoiceMute ? (
          <Tooltip title={isLiveVoiceMuted ? liveVoiceLabels.unmute : liveVoiceLabels.mute} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button
              type="button"
              className={cx('areqa-chat-input-voice-button', styles.iconButton, styles.voiceButton)}
              onClick={onToggleLiveVoiceMute}
              aria-label={isLiveVoiceMuted ? liveVoiceLabels.unmute : liveVoiceLabels.mute}
            >
              {isLiveVoiceMuted ? <MicOff size={18} /> : <Mic size={18} />}
            </button>
          </Tooltip>
        ) : onOpenLiveTutor && !hasComposerContent ? (
          <Tooltip title={liveVoiceLabels.open} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button
              type="button"
              className={cx('areqa-chat-input-voice-button', styles.iconButton, styles.voiceButton)}
              onClick={onOpenLiveTutor}
              disabled={disabled || hasComposerContent}
              aria-label={liveVoiceLabels.open}
            >
              <AudioLines size={20} />
            </button>
          </Tooltip>
        ) : null}
        {dictationState !== 'idle' ? null : isLiveVoiceActive && onToggleLiveVoiceAvatar ? (
          <Tooltip
            title={isLiveVoiceAvatarEnabled ? liveVoiceLabels.avatarOff : liveVoiceLabels.avatarOn}
            color="#262626"
            styles={{ container: { color: '#ffffff' } }}
          >
            <button
              type="button"
              className={cx(
                'areqa-chat-input-avatar-button',
                styles.iconButton,
                styles.avatarButton,
                !isLiveVoiceAvatarEnabled && styles.avatarButtonInactive,
              )}
              onClick={onToggleLiveVoiceAvatar}
              aria-label={isLiveVoiceAvatarEnabled ? liveVoiceLabels.avatarOff : liveVoiceLabels.avatarOn}
            >
              {isLiveVoiceAvatarEnabled ? <Video size={18} /> : <VideoOff size={18} />}
            </button>
          </Tooltip>
        ) : null}
        {dictationState !== 'idle' ? null : showStop ? (
          <button
            type="button"
            className={cx('areqa-chat-input-send-button', styles.iconButton, styles.sendButton, styles.stopButton)}
            onClick={onStop}
            aria-label={t('stopGenerating')}
          >
            <Square size={16} fill="currentColor" />
          </button>
        ) : isLiveVoiceActive && onCloseLiveVoice ? (
          <Tooltip title={liveVoiceLabels.close} color="#262626" styles={{ container: { color: '#ffffff' } }}>
            <button
              type="button"
              className={cx('areqa-chat-input-send-button', styles.iconButton, styles.sendButton, styles.liveVoiceCloseButton)}
              onClick={onCloseLiveVoice}
              aria-label={liveVoiceLabels.close}
            >
              <X size={20} />
            </button>
          </Tooltip>
        ) : canSend || !onOpenLiveTutor ? (
          <button
            type="button"
            className={cx('areqa-chat-input-send-button', styles.iconButton, styles.sendButton)}
            onClick={handleSend}
            disabled={!canSend}
            aria-label={t('sendMessage')}
          >
            <ArrowUp size={20} />
          </button>
        ) : null}
        {dictationState === 'idle' && isLiveVoiceActive && canSend && (
          <button
            type="button"
            className={cx('areqa-chat-input-send-button', styles.iconButton, styles.sendButton)}
            onClick={handleSend}
            aria-label={t('sendMessage')}
          >
            <ArrowUp size={20} />
          </button>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,text/plain,text/markdown,.txt,.md"
        multiple
        hidden
        onChange={handleAttachmentChange}
        aria-label={t('chooseAttachment')}
      />

      {hasMath && (
        <div className={cx('areqa-chat-input-math-preview', styles.mathPreview)} aria-label={t('latexPreview')}>
          <div className={cx('areqa-chat-input-math-preview-label', styles.mathPreviewLabel)}>{t('formulaPreview')}</div>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }], rehypeMathSource]}
          >
            {normalizeDisplayMathBlocks(value)}
          </ReactMarkdown>
        </div>
      )}

    </div>
    </>
  );
}

export default ChatInput;
