/**
 * Database Service
 * Unified interface for all database operations
 * Provides repository access, settings management, and data import/export
 */

import { conversationRepo } from '@/database/repositories/conversationRepo';
import { messageRepo } from '@/database/repositories/messageRepo';
import { db } from '@/database/db';
import type { Conversation, Message, Setting } from '@/database/schema';
import { logger } from '@/utils/logger';

/** Current export format version */
const EXPORT_VERSION = 1;

/**
 * Database export format interface
 */
interface ExportedData {
  version: number;
  exportedAt: string;
  data: {
    conversations: Conversation[];
    messages: Message[];
    settings: Setting[];
  };
}

/**
 * Validation result type
 */
interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Validates that a value is a valid Date or can be converted to one
 */
function isValidDate(value: unknown): boolean {
  if (value instanceof Date) return !isNaN(value.getTime());
  if (typeof value === 'string' || typeof value === 'number') {
    const date = new Date(value);
    return !isNaN(date.getTime());
  }
  return false;
}

/**
 * Validates a conversation object
 */
function validateConversation(conv: unknown): ValidationResult {
  if (!conv || typeof conv !== 'object') {
    return { valid: false, error: 'Conversation must be an object' };
  }

  const c = conv as Record<string, unknown>;

  if (typeof c.id !== 'string' || c.id.length === 0) {
    return { valid: false, error: 'Conversation must have a valid id' };
  }

  if (typeof c.title !== 'string') {
    return { valid: false, error: 'Conversation must have a title' };
  }

  if (!isValidDate(c.createdAt)) {
    return { valid: false, error: 'Conversation must have a valid createdAt date' };
  }

  if (!isValidDate(c.updatedAt)) {
    return { valid: false, error: 'Conversation must have a valid updatedAt date' };
  }

  if (typeof c.messageCount !== 'number' || c.messageCount < 0) {
    return { valid: false, error: 'Conversation must have a valid messageCount' };
  }

  return { valid: true };
}

/**
 * Validates a message object
 */
function validateMessage(msg: unknown): ValidationResult {
  if (!msg || typeof msg !== 'object') {
    return { valid: false, error: 'Message must be an object' };
  }

  const m = msg as Record<string, unknown>;

  if (typeof m.id !== 'string' || m.id.length === 0) {
    return { valid: false, error: 'Message must have a valid id' };
  }

  if (typeof m.conversationId !== 'string' || m.conversationId.length === 0) {
    return { valid: false, error: 'Message must have a valid conversationId' };
  }

  if (m.role !== 'user' && m.role !== 'assistant') {
    return { valid: false, error: 'Message role must be user or assistant' };
  }

  if (typeof m.content !== 'string') {
    return { valid: false, error: 'Message must have content' };
  }

  if (!isValidDate(m.createdAt)) {
    return { valid: false, error: 'Message must have a valid createdAt date' };
  }

  return { valid: true };
}

/**
 * Validates a setting object
 */
function validateSetting(setting: unknown): ValidationResult {
  if (!setting || typeof setting !== 'object') {
    return { valid: false, error: 'Setting must be an object' };
  }

  const s = setting as Record<string, unknown>;

  if (typeof s.key !== 'string' || s.key.length === 0) {
    return { valid: false, error: 'Setting must have a valid key' };
  }

  // value can be any JSON-serializable type, so we just check it exists
  if (s.value === undefined) {
    return { valid: false, error: 'Setting must have a value' };
  }

  if (!isValidDate(s.updatedAt)) {
    return { valid: false, error: 'Setting must have a valid updatedAt date' };
  }

  return { valid: true };
}

/**
 * Validates the entire exported data structure
 */
function validateExportedData(data: unknown): ValidationResult {
  if (!data || typeof data !== 'object') {
    return { valid: false, error: 'Import data must be an object' };
  }

  const d = data as Record<string, unknown>;

  // Validate version
  if (typeof d.version !== 'number' || d.version < 1) {
    return { valid: false, error: 'Invalid export version' };
  }

  if (d.version > EXPORT_VERSION) {
    return {
      valid: false,
      error: `Export version ${d.version} is newer than supported version ${EXPORT_VERSION}`,
    };
  }

  // Validate exportedAt
  if (!isValidDate(d.exportedAt)) {
    return { valid: false, error: 'Invalid export timestamp' };
  }

  // Validate data structure
  if (!d.data || typeof d.data !== 'object') {
    return { valid: false, error: 'Missing data section' };
  }

  const dataSection = d.data as Record<string, unknown>;

  // Validate conversations array
  if (dataSection.conversations !== undefined) {
    if (!Array.isArray(dataSection.conversations)) {
      return { valid: false, error: 'Conversations must be an array' };
    }

    for (let i = 0; i < dataSection.conversations.length; i++) {
      const result = validateConversation(dataSection.conversations[i]);
      if (!result.valid) {
        return { valid: false, error: `Conversation at index ${i}: ${result.error}` };
      }
    }
  }

  // Validate messages array
  if (dataSection.messages !== undefined) {
    if (!Array.isArray(dataSection.messages)) {
      return { valid: false, error: 'Messages must be an array' };
    }

    for (let i = 0; i < dataSection.messages.length; i++) {
      const result = validateMessage(dataSection.messages[i]);
      if (!result.valid) {
        return { valid: false, error: `Message at index ${i}: ${result.error}` };
      }
    }
  }

  // Validate settings array
  if (dataSection.settings !== undefined) {
    if (!Array.isArray(dataSection.settings)) {
      return { valid: false, error: 'Settings must be an array' };
    }

    for (let i = 0; i < dataSection.settings.length; i++) {
      const result = validateSetting(dataSection.settings[i]);
      if (!result.valid) {
        return { valid: false, error: `Setting at index ${i}: ${result.error}` };
      }
    }
  }

  return { valid: true };
}

/**
 * Converts date strings to Date objects in imported data
 */
function convertDates<T>(
  items: T[],
  dateFields: string[]
): T[] {
  return items.map((item) => {
    const converted = { ...item } as T & Record<string, unknown>;
    for (const field of dateFields) {
      if (converted[field]) {
        (converted as Record<string, unknown>)[field] = new Date(converted[field] as string | number);
      }
    }
    return converted;
  });
}

export const databaseService = {
  /** Conversation repository for CRUD operations */
  conversation: conversationRepo,
  /** Message repository for CRUD operations */
  message: messageRepo,

  /**
   * Settings management
   * Key-value store for application settings
   */
  settings: {
    /**
     * Get a setting value by key
     * @param key - The setting key
     * @returns The setting value or undefined
     */
    async get<T>(key: string): Promise<T | undefined> {
      const setting = await db.settings.get(key);
      if (!setting) return undefined;

      // Type-safe return with runtime check
      return setting.value as T;
    },

    /**
     * Set a setting value
     * Creates or updates the setting
     * @param key - The setting key
     * @param value - The value to store (must be JSON serializable)
     */
    async set<T>(key: string, value: T): Promise<void> {
      const setting: Setting = {
        key,
        value,
        updatedAt: new Date(),
      };
      await db.settings.put(setting);
    },

    /**
     * Delete a setting
     * @param key - The setting key to delete
     */
    async delete(key: string): Promise<void> {
      await db.settings.delete(key);
    },
  },

  /**
   * Get storage usage estimate
   * Uses the Storage API to estimate IndexedDB usage
   * @returns Object with usage and quota in bytes
   */
  async getStorageEstimate(): Promise<{ usage: number; quota: number }> {
    if (
      typeof navigator !== 'undefined' &&
      'storage' in navigator &&
      'estimate' in navigator.storage
    ) {
      const estimate = await navigator.storage.estimate();
      return {
        usage: estimate.usage || 0,
        quota: estimate.quota || 0,
      };
    }
    return { usage: 0, quota: 0 };
  },

  /**
   * Export all database data as JSON string
   * Includes version and timestamp for compatibility checking
   * @returns JSON string of all data
   */
  async exportData(): Promise<string> {
    const conversations = await db.conversations.toArray();
    const messages = await db.messages.toArray();
    const settings = await db.settings.toArray();

    const exportedData: ExportedData = {
      version: EXPORT_VERSION,
      exportedAt: new Date().toISOString(),
      data: { conversations, messages, settings },
    };

    return JSON.stringify(exportedData, null, 2);
  },

  /**
   * Import data from JSON string with validation
   * Uses bulkPut to upsert records (creates or updates)
   * @param jsonString - JSON string from exportData()
   * @throws Error if validation fails or import encounters an error
   */
  async importData(jsonString: string): Promise<void> {
    // Parse JSON with error handling
    let parsed: unknown;
    try {
      parsed = JSON.parse(jsonString);
    } catch (parseError) {
      logger.error('Failed to parse import JSON', parseError as Error);
      throw new Error('Invalid JSON format');
    }

    // Validate the structure
    const validation = validateExportedData(parsed);
    if (!validation.valid) {
      logger.warn('Import validation failed', { error: validation.error });
      throw new Error(`Import validation failed: ${validation.error}`);
    }

    const exportedData = parsed as ExportedData;
    const { data } = exportedData;

    // Perform import in a transaction with rollback on error
    try {
      await db.transaction('rw', [db.conversations, db.messages, db.settings], async () => {
        if (data.conversations && data.conversations.length > 0) {
          const conversations = convertDates(data.conversations, ['createdAt', 'updatedAt']);
          await db.conversations.bulkPut(conversations);
          logger.info('Imported conversations', { count: conversations.length });
        }

        if (data.messages && data.messages.length > 0) {
          const messages = convertDates(data.messages, ['createdAt']);
          await db.messages.bulkPut(messages);
          logger.info('Imported messages', { count: messages.length });
        }

        if (data.settings && data.settings.length > 0) {
          const settings = convertDates(data.settings, ['updatedAt']);
          await db.settings.bulkPut(settings);
          logger.info('Imported settings', { count: settings.length });
        }
      });

      logger.info('Import completed successfully');
    } catch (transactionError) {
      // Dexie automatically rolls back on transaction error
      logger.error('Import transaction failed', transactionError as Error);
      throw new Error('Import failed. Changes have been rolled back.');
    }
  },
};
