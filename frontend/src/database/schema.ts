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

/**
 * Message entity
 * Represents a single message in a conversation
 */
export interface Message {
  /** UUID v4 - Primary key */
  id: string;
  /** Foreign key - Associated conversation ID */
  conversationId: string;
  /** Message role - user or assistant */
  role: 'user' | 'assistant';
  /** Message content */
  content: string;
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
    score: number;
    chunk_id: string;
  }>;
  /** Suggested follow-up questions (optional) */
  suggestions?: string[];
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
