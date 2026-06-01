/**
 * Chat Stream API Type Definitions
 * Defines all types for API requests and responses
 */
/**
 * Message role types
 */
import type { CitationSource } from '@/components/Citations';
export type MessageRole = 'user' | 'assistant' | 'system';

/**
 * Chat message structure
 */
export interface ChatMessage {
  role: MessageRole;
  content: string;
}

/**
 * Chat Stream API request body
 */
export interface ChatStreamRequest {
  /** Model to use - 'sonar-reasoning' for reasoning with thinking */
  model: 'sonar-reasoning' | 'sonar' | 'sonar-pro';
  /** Array of messages in the conversation */
  messages: ChatMessage[];
  /** Enable streaming responses */
  stream?: boolean;
  /** Maximum tokens to generate */
  max_tokens?: number;
  /** Temperature for response randomness (0-2) */
  temperature?: number;
  /** Top-p sampling parameter */
  top_p?: number;
  /** Frequency penalty */
  frequency_penalty?: number;
  /** Presence penalty */
  presence_penalty?: number;
}

/**
 * Search result from Perplexity
 */
export interface SearchResult {
  /** Title of the source */
  title: string;
  /** URL of the source */
  url: string;
  /** Snippet/excerpt from the source */
  snippet: string;
}

/**
 * Token usage information
 */
export interface UsageInfo {
  /** Tokens used in the prompt */
  prompt_tokens: number;
  /** Tokens generated in completion */
  completion_tokens: number;
  /** Total tokens used */
  total_tokens: number;
  /** Search context size used */
  search_context_size?: 'low' | 'medium' | 'high';
}

/**
 * Non-streaming response choice
 */
export interface ResponseChoice {
  index: number;
  finish_reason: 'stop' | 'length' | null;
  message: {
    role: 'assistant';
    content: string;
  };
}

/**
 * Streaming response delta
 */
export interface StreamDelta {
  role?: 'assistant';
  content?: string;
}

/**
 * Streaming response choice
 */
export interface StreamChoice {
  index: number;
  delta: StreamDelta;
  finish_reason: 'stop' | 'length' | null;
}

/**
 * Chat Stream API non-streaming response
 */
export interface ChatStreamResponse {
  /** Unique response ID */
  id: string;
  /** Model used */
  model: string;
  /** Response choices */
  choices: ResponseChoice[];
  /** Citation URLs */
  citations?: string[];
  /** Detailed search results */
  search_results?: SearchResult[];
  /** Token usage */
  usage: UsageInfo;
}

/**
 * Chat Stream API streaming chunk
 */
export interface ChatStreamStreamChunk {
  /** Unique response ID */
  id: string;
  /** Model used */
  model?: string;
  /** Stream choices with delta */
  choices: StreamChoice[];
  /** Citation URLs (usually in final chunk) */
  citations?: string[];
  /** Search results (usually in final chunk) */
  search_results?: SearchResult[];
  /** Usage info (usually in final chunk) */
  usage?: UsageInfo;
}

/**
 * Parsed chunk types from ThinkTagParser
 */
export type ParsedChunkType =
  | 'thinking_start'
  | 'thinking_content'
  | 'thinking_end'
  | 'content'
  | 'done';

/**
 * Parsed chunk from the think tag parser
 */
export interface ParsedChunk {
  type: ParsedChunkType;
  content?: string;
}

/**
 * Callbacks for streaming chat responses
 */
export interface StreamCallbacks {
  /** Called when <think> tag starts */
  onThinkingStart: () => void;
  /** Called with thinking content */
  onThinkingContent: (content: string) => void;
  /** Called when </think> tag ends */
  onThinkingEnd: () => void;
  /** Called with answer content (after thinking) */
  onContent: (content: string) => void;
  /** Called with citation URLs */
  onCitations: (citations: string[]) => void;
  /** Called when stream completes */
  onDone: (suggestions?: string[]) => void;
  /** Called on error */
  onError: (error: Error) => void;
  /** Called when RAG pipeline status changes */
  onStatus?: (status: 'idle' | 'retrieving' | 'searching_dense' | 'searching_sparse' | 'reranking' | 'sources_ready' | 'generating' | 'done', message: string) => void;
  /** Called when structured sources payload is pushed */
  onSources?: (sources: CitationSource[]) => void;
  /** Called when suggested follow-up questions are received */
  onSuggestions?: (suggestions: string[]) => void;
}
