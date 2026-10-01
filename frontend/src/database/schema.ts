/**
 * Database schema definitions
 * Defines the structure of all database tables
 */

/**
 * Conversation entity
 * Represents a chat conversation session
 */
export interface Conversation {
  /** UUID v4 - Primary key */
  id: string;
  /** User ID - Multi-tenant support */
  userId: string;
  /** Conversation title (auto-generated from first message) */
  title: string;
  /** Creation timestamp */
  createdAt: Date;
  /** Last update timestamp */
  updatedAt: Date;
  /** Total message count in this conversation */
  messageCount: number;
  /** Preview of the last message (first 100 characters) */
  lastMessagePreview: string;
}

/** Safe, display-only metadata for a request-scoped chat attachment. */
export interface AttachmentMetadata {
  /** Sanitized display filename; file bytes are never persisted. */
  name: string;
  /** Browser-provided MIME type after client validation. */
  mediaType: string;
  /** Original file size in bytes. */
  sizeBytes: number;
}

export type MessageFeedback = 'liked' | 'disliked';
export type MessageFeedbackReason =
  | 'incorrect_or_incomplete'
  | 'not_what_i_wanted'
  | 'slow_or_broken'
  | 'style_or_tone'
  | 'safety_or_legal'
  | 'other';

export interface MessageFeedbackDetails {
  reason?: MessageFeedbackReason | null;
  comment?: string | null;
}

/**
 * Structured display blocks for illustrated assistant answers.
 *
 * Compatibility:
 * - `Message.content` remains the plain-text fallback and copy/export source.
 * - Blocks are display metadata produced by the backend; user-authored Markdown
 *   image URLs are not promoted into this structure.
 */
export type AnswerBlock = ParagraphBlock | ImageBlock;

/** Text paragraph rendered through the existing safe Markdown renderer. */
export interface ParagraphBlock {
  type: 'paragraph';
  text: string;
}

/** Verified image card rendered inline with source attribution. */
export interface ImageBlock {
  type: 'image_block';
  slotId: string;
  topic: string;
  purpose: 'diagram' | 'photo' | 'portrait' | 'chart' | 'example' | string;
  imageUrl: string;
  thumbnailUrl?: string;
  sourceUrl: string;
  sourceDomain: string;
  caption: string;
  provider?: 'wikimedia' | 'openverse' | 'og_image' | 'cache' | 'tavily_images' | 'serpapi_images' | 'perplexity_images' | 'pdf_attachment' | string;
  /** Safe provider model identifier for generated images. */
  model?: string;
  /** Bounded drawing intent and reference brief, retained for image retries without raw files. */
  generationRequest?: {
    prompt: string;
    language: 'zh-TW' | 'zh-CN' | 'en';
    referenceBrief?: string;
    conversationContext?: string;
    /** Failed/cancelled attachment preparation must be retried with the files. */
    requiresReference?: boolean;
  };
  tier?: 'wikimedia' | 'openverse' | 'og_image' | 'cache' | 'tavily_images' | 'serpapi_images' | 'perplexity_images' | 'pdf_attachment' | string;
  license?: string;
  licenseUrl?: string;
  creator?: string;
  attributionString?: string;
  attributionCaption?: string;
  explanatoryCaption?: string;
  visionSummary?: string;
  visibleElements?: string[];
  howToRead?: string[];
  visionConfidence?: 'high' | 'medium' | 'low' | 'unknown' | string;
  visionLimitations?: string[];
  visionSource?: 'vision_model' | 'missing_model_client' | 'invalid_image_url' | 'provider_unavailable' | string;
  /** Backend-owned bucket for persisted PDF visual images. */
  storageBucket?: string;
  /** Backend-owned object path for persisted PDF visual images. */
  storagePath?: string;
  /** Unix timestamp when the signed display URL expires. */
  storageExpiresAt?: number;
  transient?: boolean;
  status?: 'pending' | 'resolved' | 'error';
  /** Backend phase; percentages are never inferred from elapsed time. */
  generationState?: 'accepted' | 'preparing_reference' | 'generating' | 'storing';
  width?: number;
  height?: number;
  safetyStatus: 'pass' | 'flagged' | 'unavailable';
  matchConfidence: number;
  heuristicScore?: number;
  pedagogicalScore?: number;
}

/**
 * Message entity
 * Represents a single message in a conversation
 */
export interface Message {
  /** UUID v4 - Primary key */
  id: string;
  /** User ID - Multi-tenant support */
  userId: string;
  /** Foreign key - Associated conversation ID */
  conversationId: string;
  /** Message role - user or assistant */
  role: 'user' | 'assistant';
  /** Message content */
  content: string;
  /** Display-only attachment metadata (never binary data or extracted text). */
  attachments?: AttachmentMetadata[];
  /** AI reasoning/thinking process (optional) */
  reasoning?: {
    /** Thinking process content */
    content: string;
    /** Time spent thinking in milliseconds */
    duration?: number;
  };
  /** Citation URLs from search results (optional) */
  citations?: string[];
  /** Detailed search results (optional) */
  searchResults?: Array<{
    title: string;
    url: string;
    snippet: string;
  }>;
  /** Structured RAG sources (optional) */
  sources?: Array<{
    title: string;
    snippet: string;
    score?: number;
    chunk_id: string;
    url?: string;
  }>;
  /** Structured paragraph and image blocks for illustrated answers. */
  answerBlocks?: AnswerBlock[];
  /** Suggested follow-up questions (optional) */
  suggestions?: string[];
  /** User feedback for assistant messages. */
  feedback?: MessageFeedback | null;
  /** Categorized reason for negative assistant feedback. */
  feedbackReason?: MessageFeedbackReason | null;
  /** Optional user-written feedback details. */
  feedbackComment?: string | null;
  /** Timestamp for the latest feedback change. */
  feedbackUpdatedAt?: Date | null;
  /** Token usage information (optional) */
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    searchContextSize: 'low' | 'medium' | 'high';
  };
  /** Creation timestamp */
  createdAt: Date;
  /** Last local/cloud content or metadata edit timestamp. */
  updatedAt?: Date;
}

/**
 * Local-only delete marker for a message.
 *
 * Compatibility:
 * - Supabase currently has no durable message tombstone table.
 * - The browser keeps this marker past the matching cloud delete so stale
 *   pull snapshots cannot recreate a user-deleted turn.
 */
export interface MessageDeletion {
  /** Message ID being deleted. */
  id: string;
  /** User ID that owns the deleted message. */
  userId: string;
  /** Conversation that owned the deleted message, if known. */
  conversationId: string | null;
  /** Local deletion timestamp. */
  deletedAt: Date;
  /** Number of attempted cloud delete calls. */
  retryCount: number;
  /** Last safe error summary from cloud delete, if any. */
  lastError?: string | null;
}

/**
 * Local-only marker for message rows that still need cloud sync.
 *
 * Compatibility:
 * - The queue stores only identifiers, timestamps, and safe error summaries.
 * - The latest message body is read from `messages` immediately before push,
 *   so queued work cannot replay stale edited content.
 */
export interface MessageSyncQueueItem {
  /** Message ID to push. */
  id: string;
  /** User ID that owns the pending message. */
  userId: string;
  /** Conversation that owns the pending message. */
  conversationId: string;
  /** When this message was last queued for cloud sync. */
  queuedAt: Date;
  /** Local message updatedAt snapshot that the queue must cover. */
  updatedAt: Date;
  /** Number of failed cloud push attempts for this pending row. */
  retryCount: number;
  /** Last safe error summary from cloud push, if any. */
  lastError?: string | null;
}

/**
 * Local-only marker for conversation rows that still need cloud sync.
 *
 * Compatibility:
 * - Conversation creation/title updates must survive reloads before Supabase
 *   acknowledges them.
 * - The latest conversation row is read from `conversations` immediately
 *   before push, so queued work cannot replay stale titles or timestamps.
 */
export interface ConversationSyncQueueItem {
  /** Conversation ID to push. */
  id: string;
  /** User ID that owns the pending conversation. */
  userId: string;
  /** When this conversation was last queued for cloud sync. */
  queuedAt: Date;
  /** Local conversation updatedAt snapshot that the queue must cover. */
  updatedAt: Date;
  /** Number of failed cloud push attempts for this pending row. */
  retryCount: number;
  /** Last safe error summary from cloud push, if any. */
  lastError?: string | null;
}

/**
 * User-saved note linked to an assistant response.
 *
 * Compatibility:
 * - Notes keep a message/conversation reference for navigation and sync.
 * - A content snapshot is retained so the note remains readable if the source
 *   conversation is deleted locally or is unavailable offline.
 */
export interface Note {
  /** UUID v4 - Primary key */
  id: string;
  /** User ID - Multi-tenant support */
  userId: string;
  /** Source conversation ID */
  conversationId: string | null;
  /** Source assistant message ID */
  messageId: string | null;
  /** Conversation title captured when the note was created or synced. */
  conversationTitle?: string | null;
  /** Assistant response snapshot used for offline and deleted-source fallback. */
  contentSnapshot: string;
  /** Structured paragraph and image blocks captured from the assistant response. */
  answerBlocksSnapshot?: AnswerBlock[];
  /** Citation URLs captured from the assistant response. */
  citationsSnapshot?: string[];
  /** Structured RAG sources captured from the assistant response. */
  sourcesSnapshot?: Message['sources'];
  /** User-authored lightweight organization labels. */
  tags?: string[];
  /** Whether the note should stay in the pinned group. */
  isPinned?: boolean;
  /** Creation timestamp */
  createdAt: Date;
  /** Last update timestamp */
  updatedAt: Date;
}

/**
 * Setting entity
 * Stores application settings as key-value pairs
 */
export interface Setting {
  /** Setting key - Primary key */
  key: string;
  /** Setting value (JSON serializable) */
  value: unknown;
  /** Last update timestamp */
  updatedAt: Date;
}
