'use client';

/**
 * Notes Panel
 * Displays user-saved assistant response notes.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { App, Input, Popconfirm, Spin } from 'antd';
import { NotebookText, RefreshCw, Trash2, X, MessageSquare } from 'lucide-react';
import { useNotesStore } from '@/store/notes';
import { useAuthStore } from '@/store/auth';
import { switchConversation } from '@/services/chat';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { formatUserDate } from '@/utils/dateTime';
import { requestSourceMessageFocus } from '@/utils/messageFocus';
import { useStyles } from './styles';
import type { Note } from '@/database/schema';

interface NotesPanelProps {
  onClose: () => void;
}

export function NotesPanel({ onClose }: NotesPanelProps) {
  const { styles } = useStyles();
  const { message } = App.useApp();
  const { t } = useUserPreferences();
  const user = useAuthStore((state) => state.user);
  const { notes, loading, loadNotes, deleteNote } = useNotesStore();
  const [query, setQuery] = useState('');

  useEffect(() => {
    void loadNotes(user?.id);
  }, [loadNotes, user?.id]);

  const filteredNotes = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return notes;
    return notes.filter((note) => {
      const haystack = `${note.conversationTitle ?? ''}\n${note.contentSnapshot}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [notes, query]);

  const handleOpenSource = async (note: Note) => {
    if (!note.conversationId) {
      message.error(t('notesOpenSourceFailed'));
      return;
    }

    try {
      if (note.messageId) {
        requestSourceMessageFocus(note.conversationId, note.messageId);
      }
      await switchConversation(note.conversationId);
      onClose();
    } catch {
      message.error(t('notesOpenSourceFailed'));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteNote(id);
      message.success(t('noteDeleted'));
    } catch {
      message.error(t('noteDeleteFailed'));
    }
  };

  return (
    <section className={styles.panel} aria-label={t('notesTitle')}>
      <button className={styles.closeButton} onClick={onClose} title={t('closePanel')} type="button">
        <X size={18} />
      </button>
      <div className={styles.content}>
        <header className={styles.header}>
          <div className={styles.titleRow}>
            <NotebookText size={24} />
            <h2>{t('notesTitle')}</h2>
          </div>
          <button className={styles.actionButton} disabled={loading} onClick={() => loadNotes(user?.id)} type="button">
            <RefreshCw size={15} />
            <span>{t('refresh')}</span>
          </button>
        </header>

        <Input.Search
          allowClear
          className={styles.searchInput}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('notesSearchPlaceholder')}
          value={query}
        />

        {loading ? (
          <div className={styles.empty}>
            <Spin />
          </div>
        ) : filteredNotes.length === 0 ? (
          <div className={styles.empty}>{t('notesEmpty')}</div>
        ) : (
          <div className={styles.list}>
            {filteredNotes.map((note) => (
              <article className={styles.noteCard} key={note.id}>
                <div className={styles.noteMeta}>
                  <span className={styles.noteSource}>
                    {note.conversationTitle || t('notesUntitledConversation')}
                  </span>
                  <time dateTime={note.createdAt.toISOString()}>
                    {formatUserDate(note.createdAt, {
                      year: 'numeric',
                      month: 'numeric',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </time>
                </div>
                <div className={styles.noteBody}>{note.contentSnapshot}</div>
                <div className={styles.noteTools}>
                  <button
                    className={styles.actionButton}
                    disabled={!note.conversationId}
                    onClick={() => handleOpenSource(note)}
                    type="button"
                  >
                    <MessageSquare size={15} />
                    <span>{t('openSourceConversation')}</span>
                  </button>
                  <Popconfirm
                    onConfirm={() => handleDelete(note.id)}
                    title={t('deleteNoteConfirm')}
                  >
                    <button className={styles.actionButton} type="button">
                      <Trash2 size={15} />
                      <span>{t('delete')}</span>
                    </button>
                  </Popconfirm>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
