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
  purpose: 'diagram' | 'photo' | 'portrait' | 'chart' | 'example';
  imageUrl: string;
  thumbnailUrl?: string;
  sourceUrl: string;
  sourceDomain: string;
  caption: string;
  provider?: 'wikimedia' | 'openverse' | 'og_image' | 'cache';
  license?: string;
  licenseUrl?: string;
  creator?: string;
  attributionString?: string;
  width?: number;
  height?: number;
  safetyStatus: 'pass' | 'flagged' | 'unavailable';
  matchConfidence: number;
  heuristicScore?: number;
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
