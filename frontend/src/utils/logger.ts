/**
 * Structured Error Logging Utility
 * Provides consistent logging format with context
 * Avoids exposing sensitive information in logs
 */

/** Log levels */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/** Log entry structure */
interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: Record<string, unknown>;
  error?: {
    name: string;
    message: string;
    stack?: string;
  };
}

/** Sensitive keys that should be redacted */
const SENSITIVE_KEYS = [
  'api_key',
  'apiKey',
  'api-key',
  'authorization',
  'password',
  'secret',
  'token',
  'key',
  'credential',
];

/**
 * Redacts sensitive information from an object
 * @param obj - Object to redact
 * @returns Object with sensitive values replaced
 */
function redactSensitive(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(obj)) {
    const lowerKey = key.toLowerCase();
    const isSensitive = SENSITIVE_KEYS.some((sk) => lowerKey.includes(sk));

    if (isSensitive) {
      result[key] = '[REDACTED]';
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      result[key] = redactSensitive(value as Record<string, unknown>);
    } else {
      result[key] = value;
    }
  }

  return result;
}

/**
 * Formats a log entry as JSON string
 * @param entry - Log entry to format
 * @returns Formatted JSON string
 */
function formatLogEntry(entry: LogEntry): string {
  return JSON.stringify(entry);
}

/**
 * Logger instance with structured logging methods
 */
export const logger = {
  /**
   * Log debug message
   * @param message - Log message
   * @param context - Optional context data
   */
  debug(message: string, context?: Record<string, unknown>): void {
    if (process.env.NODE_ENV === 'production') return;

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'debug',
      message,
      context: context ? redactSensitive(context) : undefined,
    };
    console.debug(formatLogEntry(entry));
  },

  /**
   * Log info message
   * @param message - Log message
   * @param context - Optional context data
   */
  info(message: string, context?: Record<string, unknown>): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'info',
      message,
      context: context ? redactSensitive(context) : undefined,
    };
    console.info(formatLogEntry(entry));
  },

  /**
   * Log warning message
   * @param message - Log message
   * @param context - Optional context data
   */
  warn(message: string, context?: Record<string, unknown>): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'warn',
      message,
      context: context ? redactSensitive(context) : undefined,
    };
    console.warn(formatLogEntry(entry));
  },

  /**
   * Log error with optional error object
   * @param message - Error message
   * @param error - Optional error object
   * @param context - Optional context data
   */
  error(message: string, error?: Error, context?: Record<string, unknown>): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: 'error',
      message,
      context: context ? redactSensitive(context) : undefined,
      error: error
        ? {
            name: error.name,
            message: error.message,
            stack: process.env.NODE_ENV !== 'production' ? error.stack : undefined,
          }
        : undefined,
    };
    console.error(formatLogEntry(entry));
  },
};
