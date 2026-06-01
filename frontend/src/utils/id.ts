/**
 * UUID generation utility
 * Provides a consistent way to generate unique identifiers
 */

import { v4 as uuidv4 } from 'uuid';

/**
 * Generates a UUID v4 string
 * @returns A unique identifier string
 */
export function generateUUID(): string {
  return uuidv4();
}
