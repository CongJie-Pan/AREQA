/**
 * Note Repository
 * Provides CRUD operations for notes linked to assistant messages.
 */

import { db, getCurrentUserId } from '../db';
import type { Message, Note } from '../schema';
import { generateUUID } from '@/utils/id';
import { syncService } from '@/services/syncService';

export type AddNoteData = Omit<Note, 'id' | 'userId' | 'createdAt' | 'updatedAt'> & {
  id?: string;
  createdAt?: Date;
  updatedAt?: Date;
  conversationId: string;
  messageId: string;
};

export interface UpdateNoteMetadataData {
  tags?: string[];
  isPinned?: boolean;
}

export interface UpdateNoteContentResult {
  note: Note;
  sourceMessage?: Message;
}

function normalizeTags(tags: string[] | undefined): string[] {
  if (!tags) return [];

  const seen = new Set<string>();
  return tags
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0)
    .filter((tag) => {
      const key = tag.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 12);
}

/**
 * Builds a persisted note from an assistant response.
 *
 * Args:
 *   message: Source assistant message to save.
 *   conversationTitle: Optional source conversation title snapshot.
 *
 * Returns:
 *   Note payload ready for local persistence and cloud sync.
 *
 * Raises:
 *   Error: If the source is not an assistant reply or has no readable content.
 */
function buildNoteFromMessage(message: Message, conversationTitle?: string | null): AddNoteData {
  if (message.role !== 'assistant') {
    throw new Error('Only assistant replies can be saved as notes');
  }

  if (!message.content.trim() && (!message.answerBlocks || message.answerBlocks.length === 0)) {
    throw new Error('Cannot save an empty assistant reply as a note');
  }

  return {
    conversationId: message.conversationId,
    messageId: message.id,
    conversationTitle: conversationTitle ?? null,
    contentSnapshot: message.content,
    answerBlocksSnapshot: message.answerBlocks,
    citationsSnapshot: message.citations,
    sourcesSnapshot: message.sources,
    tags: [],
    isPinned: false,
  };
}

export const noteRepo = {
  /**
   * Adds a note and pushes it to Supabase for authenticated users.
   *
   * Args:
   *   noteData: User-owned note payload.
   *
   * Returns:
   *   The created or existing note. Duplicate message notes are idempotent for
   *   the current user so repeated clicks do not create duplicate rows.
   *
   * Raises:
   *   Error: If no authenticated user is available for local ownership.
   */
  async add(noteData: AddNoteData): Promise<Note> {
    const userId = getCurrentUserId();
    if (!userId) throw new Error('Authentication required to persist notes');

    const existing = await db.notes
      .where('[userId+messageId]')
      .equals([userId, noteData.messageId])
      .first();
    if (existing) return existing;

    const now = new Date();
    const note: Note = {
      id: noteData.id ?? generateUUID(),
      userId,
      conversationId: noteData.conversationId,
      messageId: noteData.messageId,
      conversationTitle: noteData.conversationTitle ?? null,
      contentSnapshot: noteData.contentSnapshot,
      answerBlocksSnapshot: noteData.answerBlocksSnapshot,
      citationsSnapshot: noteData.citationsSnapshot,
      sourcesSnapshot: noteData.sourcesSnapshot,
      tags: normalizeTags(noteData.tags),
      isPinned: Boolean(noteData.isPinned),
      createdAt: noteData.createdAt ?? now,
      updatedAt: noteData.updatedAt ?? now,
    };

    await db.notes.add(note);
    syncService.pushNote(note);
    return note;
  },

  /**
   * Saves an assistant response as a note.
   *
   * Args:
   *   message: Source assistant message.
   *   conversationTitle: Optional source title snapshot.
   *
   * Returns:
   *   The created or existing note for that message.
   */
  async addFromMessage(message: Message, conversationTitle?: string | null): Promise<Note> {
    return this.add(buildNoteFromMessage(message, conversationTitle));
  },

  /**
   * Gets all notes for one user ordered by creation time descending.
   */
  async getAll(userId: string): Promise<Note[]> {
    const notes = await db.notes.where('userId').equals(userId).sortBy('createdAt');
    return notes.reverse();
  },

  /**
   * Checks whether a message has already been saved as a note by this user.
   */
  async existsByMessageId(messageId: string, userId: string): Promise<boolean> {
    const existing = await db.notes
      .where('[userId+messageId]')
      .equals([userId, messageId])
      .first();
    return Boolean(existing);
  },

  /**
   * Updates user-owned note organization metadata and syncs it to Supabase.
   */
  async updateMetadata(id: string, updates: UpdateNoteMetadataData): Promise<Note> {
    const existing = await db.notes.get(id);
    if (!existing) throw new Error('Note not found');

    const updatedNote: Note = {
      ...existing,
      tags: updates.tags ? normalizeTags(updates.tags) : normalizeTags(existing.tags),
      isPinned: updates.isPinned ?? Boolean(existing.isPinned),
      updatedAt: new Date(),
    };

    await db.notes.put(updatedNote);
    syncService.pushNote(updatedNote);
    return updatedNote;
  },

  /**
   * Mirrors the latest source assistant message into its linked note.
   *
   * Args:
   *   message: Updated assistant message that may already be saved as a note.
   *
   * Returns:
   *   The updated note, or null when no note is linked to the message.
   */
  async syncFromMessage(message: Message): Promise<Note | null> {
    const userId = getCurrentUserId();
    if (!userId) return null;
    if (message.role !== 'assistant') {
      throw new Error('Only assistant replies can sync note content');
    }

    const existing = await db.notes
      .where('[userId+messageId]')
      .equals([userId, message.id])
      .first();
    if (!existing) return null;

    const updatedNote: Note = {
      ...existing,
      contentSnapshot: message.content,
      answerBlocksSnapshot: message.answerBlocks,
      citationsSnapshot: message.citations,
      sourcesSnapshot: message.sources,
      updatedAt: new Date(),
    };

    await db.notes.put(updatedNote);
    syncService.pushNote(updatedNote);
    return updatedNote;
  },

  /**
   * Updates a note body and mirrors the edited Markdown back to the source
   * assistant message when that message still exists locally.
   *
   * Args:
   *   id: Note ID to update.
   *   content: User-authored Markdown body.
   *
   * Returns:
   *   The updated note and, when found, the updated source assistant message.
   *
   * Raises:
   *   Error: If the note does not exist or the content is empty.
   */
  async updateContentAndSourceMessage(id: string, content: string): Promise<UpdateNoteContentResult> {
    const existing = await db.notes.get(id);
    if (!existing) throw new Error('Note not found');

    const normalizedContent = content.trim();
    if (!normalizedContent) throw new Error('Note content cannot be empty');

    const now = new Date();
    let updatedSourceMessage: Message | undefined;
    const updatedNote: Note = {
      ...existing,
      contentSnapshot: normalizedContent,
      answerBlocksSnapshot: undefined,
      updatedAt: now,
    };

    await db.transaction('rw', [db.notes, db.messages], async () => {
      if (existing.messageId) {
        const sourceMessage = await db.messages.get(existing.messageId);
        if (sourceMessage?.role === 'assistant') {
          updatedSourceMessage = {
            ...sourceMessage,
            content: normalizedContent,
            answerBlocks: undefined,
          };
          await db.messages.put(updatedSourceMessage);
        }
      }

      await db.notes.put(updatedNote);
    });

    syncService.pushNote(updatedNote);
    if (updatedSourceMessage) {
      syncService.pushMessage(updatedSourceMessage);
    }

    return { note: updatedNote, sourceMessage: updatedSourceMessage };
  },

  /**
   * Deletes one note locally and in Supabase for the current user.
   */
  async delete(id: string): Promise<void> {
    await db.notes.delete(id);
    syncService.deleteNote(id);
  },

  /**
   * Removes legacy guest notes without affecting authenticated users.
   */
  async clearGuestData(): Promise<void> {
    await db.notes.where('userId').equals('default_user').delete();
  },
};
