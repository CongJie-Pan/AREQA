/**
 * Validation and Sanitization Utilities
 * Provides input validation and XSS protection for user content
 */

/** Maximum allowed message content length (100KB) */
export const MAX_MESSAGE_LENGTH = 100_000;

/** Maximum allowed messages per request */
export const MAX_MESSAGES_PER_REQUEST = 100;

/**
 * Sanitizes user input to prevent XSS attacks
 * Escapes HTML special characters
 * @param input - Raw user input
 * @returns Sanitized string safe for storage and display
 */
export function sanitizeInput(input: string): string {
  if (typeof input !== 'string') {
    return '';
  }

  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

/**
 * Validates message content
 * @param content - Message content to validate
 * @returns Validation result with error message if invalid
 */
export function validateMessageContent(content: unknown): {
  valid: boolean;
  error?: string;
  sanitized?: string;
} {
  if (typeof content !== 'string') {
    return { valid: false, error: 'Message content must be a string' };
  }

  if (content.length === 0) {
    return { valid: false, error: 'Message content cannot be empty' };
  }

  if (content.length > MAX_MESSAGE_LENGTH) {
    return {
      valid: false,
      error: `Message content exceeds maximum length of ${MAX_MESSAGE_LENGTH} characters`,
    };
  }

  return { valid: true, sanitized: sanitizeInput(content) };
}

/**
 * Validates chat message structure
 * @param message - Message object to validate
 * @returns Validation result
 */
export function validateChatMessage(message: unknown): {
  valid: boolean;
  error?: string;
} {
  if (!message || typeof message !== 'object') {
    return { valid: false, error: 'Message must be an object' };
  }

  const msg = message as Record<string, unknown>;

  if (!msg.role || typeof msg.role !== 'string') {
    return { valid: false, error: 'Message must have a valid role' };
  }

  if (!['user', 'assistant', 'system'].includes(msg.role)) {
    return { valid: false, error: 'Message role must be user, assistant, or system' };
  }

  const contentValidation = validateMessageContent(msg.content);
  if (!contentValidation.valid) {
    return { valid: false, error: contentValidation.error };
  }

  return { valid: true };
}

/**
 * Validates an array of chat messages
 * @param messages - Array of messages to validate
 * @returns Validation result with detailed error
 */
export function validateMessagesArray(messages: unknown): {
  valid: boolean;
  error?: string;
} {
  if (!Array.isArray(messages)) {
    return { valid: false, error: 'Messages must be an array' };
  }

  if (messages.length === 0) {
    return { valid: false, error: 'Messages array cannot be empty' };
  }

  if (messages.length > MAX_MESSAGES_PER_REQUEST) {
    return {
      valid: false,
      error: `Too many messages. Maximum is ${MAX_MESSAGES_PER_REQUEST}`,
    };
  }

  for (let i = 0; i < messages.length; i++) {
    const validation = validateChatMessage(messages[i]);
    if (!validation.valid) {
      return { valid: false, error: `Message at index ${i}: ${validation.error}` };
    }
  }

  return { valid: true };
}

/**
 * Type guard for checking if a value is a valid role
 */
export function isValidRole(role: unknown): role is 'user' | 'assistant' {
  return role === 'user' || role === 'assistant';
}
