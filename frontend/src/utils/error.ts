/**
 * Error handling utilities
 * Provides consistent error normalization and custom error classes
 */

/**
 * Custom error for Chat Stream API errors
 * Includes status code and response body for debugging
 */
export class ChatStreamError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public responseBody?: unknown,
    public cause?: Error
  ) {
    super(message);
    this.name = 'ChatStreamError';
    // Maintain proper stack trace in V8 environments
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ChatStreamError);
    }
  }
}

/**
 * Custom error for stream parsing failures
 * Includes raw data for debugging
 */
export class StreamParseError extends Error {
  constructor(
    message: string,
    public rawData: string,
    public cause?: Error
  ) {
    super(message);
    this.name = 'StreamParseError';
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, StreamParseError);
    }
  }
}

/**
 * Custom error for user input validation
 */
export class ValidationError extends Error {
  constructor(
    message: string,
    public field?: string
  ) {
    super(message);
    this.name = 'ValidationError';
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ValidationError);
    }
  }
}

/**
 * Normalize any error to an Error instance
 * Useful for catch blocks where the error type is unknown
 * @param error - Unknown error value
 * @returns Normalized Error instance
 */
export function normalizeError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }
  if (typeof error === 'string') {
    return new Error(error);
  }
  return new Error(String(error));
}

/**
 * Check if an error is an abort error (user-initiated cancellation)
 * @param error - Error to check
 * @returns True if the error is an abort error
 */
export function isAbortError(error: unknown): boolean {
  if (error instanceof Error) {
    return error.name === 'AbortError' || error.message === 'Request aborted by user';
  }
  return false;
}

/**
 * Format error for logging
 * @param error - Error to format
 * @param context - Additional context
 * @returns Formatted error object
 */
export function formatErrorForLogging(
  error: Error,
  context?: Record<string, unknown>
): Record<string, unknown> {
  const formatted: Record<string, unknown> = {
    name: error.name,
    message: error.message,
    stack: error.stack,
  };

  if (error instanceof ChatStreamError) {
    formatted.statusCode = error.statusCode;
    formatted.responseBody = error.responseBody;
  }

  if (error instanceof StreamParseError) {
    formatted.rawData = error.rawData;
  }

  if (error instanceof ValidationError) {
    formatted.field = error.field;
  }

  if (context) {
    formatted.context = context;
  }

  return formatted;
}
