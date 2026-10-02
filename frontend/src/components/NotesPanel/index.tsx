'use client';

/**
 * Notes Panel
 * Displays user-saved assistant response notes.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { App, Input, Popconfirm, Spin } from 'antd';
import {
  ChevronDown,
  ChevronRight,
  Edit,
  MessageSquare,
  NotebookText,
  Pin,
  PinOff,
  RefreshCw,
  Tag,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { useNotesStore } from '@/store/notes';
import { useConversationStore } from '@/store/conversation';
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

const NOTE_SUMMARY_LIMIT = 260;
const LATIN_TEXT_PATTERN = /([A-Za-z][A-Za-z0-9'_-]*)/;

function normalizeTagInput(value: string) {
  return value.trim().replace(/\s+/g, ' ').slice(0, 32);
}

function uniqueTags(tags: string[]) {
  const seen = new Set<string>();
  return tags
    .map(normalizeTagInput)
    .filter(Boolean)
    .filter((tag) => {
      const key = tag.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 12);
}

function buildNoteSummary(content: string) {
  const normalizedContent = content.trim();
  if (normalizedContent.length <= NOTE_SUMMARY_LIMIT) {
    return { text: normalizedContent, isTruncated: false };
  }
  return {
    text: `${normalizedContent.slice(0, NOTE_SUMMARY_LIMIT).trimEnd()}...`,
    isTruncated: true,
  };
}

function renderTextWithLatinTypography(text: string, latinClassName: string) {
  return text.split(LATIN_TEXT_PATTERN).map((part, index) => (
    LATIN_TEXT_PATTERN.test(part)
      ? (
        <span className={latinClassName} key={`${part}-${index}`}>
          {part}
        </span>
      )
      : part
  ));
}

export function NotesPanel({ onClose }: NotesPanelProps) {
  const { styles } = useStyles();
  const { message } = App.useApp();
  const { t } = useUserPreferences();
  const user = useAuthStore((state) => state.user);
  const { notes: savedNotes, loading, loadNotes, updateNoteMetadata, updateNoteContent, deleteNote } = useNotesStore();
  const conversations = useConversationStore((state) => state.conversations);
  const notes = useMemo(() => {
    const conversationsById = new Map(conversations.map((conversation) => [conversation.id, conversation]));
    return savedNotes.map((note) => {
      const conversation = note.conversationId ? conversationsById.get(note.conversationId) : undefined;
      // Keep the saved title as a fallback when the source is unavailable.
      return conversation && conversation.userId === note.userId
        ? { ...note, conversationTitle: conversation.title }
        : note;
    });
  }, [savedNotes, conversations]);
  const [query, setQuery] = useState('');
  const [selectedConversationId, setSelectedConversationId] = useState('all');
  const [selectedTag, setSelectedTag] = useState('all');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set());
  const [expandedNoteIds, setExpandedNoteIds] = useState<Set<string>>(() => new Set());
  const [tagDrafts, setTagDrafts] = useState<Record<string, string>>({});
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [contentDraft, setContentDraft] = useState('');

  useEffect(() => {
    void loadNotes(user?.id);
  }, [loadNotes, user?.id]);

  const sourceOptions = useMemo(() => {
    const optionMap = new Map<string, { id: string; label: string; count: number }>();
    notes.forEach((note) => {
      const id = note.conversationId ?? 'unknown';
      const label = note.conversationTitle || t('notesUntitledConversation');
      const current = optionMap.get(id);
      optionMap.set(id, {
        id,
        label,
        count: (current?.count ?? 0) + 1,
      });
    });
    return Array.from(optionMap.values()).sort((left, right) => left.label.localeCompare(right.label));
  }, [notes, t]);

  const tagOptions = useMemo(() => (
    uniqueTags(notes.flatMap((note) => note.tags ?? []))
  ), [notes]);

  const filteredNotes = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return notes.filter((note) => {
      if (selectedConversationId !== 'all' && (note.conversationId ?? 'unknown') !== selectedConversationId) {
        return false;
      }

      if (selectedTag !== 'all' && !(note.tags ?? []).some((tag) => tag.toLowerCase() === selectedTag.toLowerCase())) {
        return false;
      }

      if (!normalizedQuery) return true;
      const haystack = `${note.conversationTitle ?? ''}\n${note.contentSnapshot}\n${(note.tags ?? []).join('\n')}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [notes, query, selectedConversationId, selectedTag]);

  const groupedNotes = useMemo(() => {
    const now = new Date();
    const pinnedNotes = filteredNotes.filter((note) => note.isPinned);
    const regularNotes = filteredNotes.filter((note) => !note.isPinned);
    const groups = new Map<string, Note[]>();

    regularNotes.forEach((note) => {
      const noteDate = note.createdAt;
      const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const startOfNoteDay = new Date(noteDate.getFullYear(), noteDate.getMonth(), noteDate.getDate());
      const diffDays = Math.floor((startOfToday.getTime() - startOfNoteDay.getTime()) / 86400000);
      const label = diffDays === 0
        ? t('today')
        : diffDays === 1
          ? t('yesterday')
          : formatUserDate(noteDate, { year: 'numeric', month: 'numeric', day: 'numeric' });

      groups.set(label, [...(groups.get(label) ?? []), note]);
    });

    return [
      ...(pinnedNotes.length > 0 ? [{ label: t('notesPinnedGroup'), notes: pinnedNotes }] : []),
      ...Array.from(groups.entries()).map(([label, groupNotes]) => ({ label, notes: groupNotes })),
    ];
  }, [filteredNotes, t]);

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

  const toggleGroup = (label: string) => {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const toggleNoteExpansion = (id: string) => {
    setExpandedNoteIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const togglePinned = async (note: Note) => {
    try {
      await updateNoteMetadata(note.id, { isPinned: !note.isPinned });
    } catch {
      message.error(t('notesUpdateFailed'));
    }
  };

  const startContentEdit = (note: Note) => {
    setEditingNoteId(note.id);
    setContentDraft(note.contentSnapshot);
  };

  const cancelContentEdit = () => {
    setEditingNoteId(null);
    setContentDraft('');
  };

  const saveContentEdit = async (note: Note) => {
    const nextContent = contentDraft.trim();
    if (!nextContent || nextContent === note.contentSnapshot.trim()) {
      cancelContentEdit();
      return;
    }

    try {
      await updateNoteContent(note.id, nextContent);
      setExpandedNoteIds((current) => new Set(current).add(note.id));
      cancelContentEdit();
    } catch {
      message.error(t('notesUpdateFailed'));
    }
  };

  const addTag = async (note: Note, rawTag: string) => {
    const tag = normalizeTagInput(rawTag);
    if (!tag) return;

    try {
      await updateNoteMetadata(note.id, { tags: uniqueTags([...(note.tags ?? []), tag]) });
      setTagDrafts((current) => ({ ...current, [note.id]: '' }));
    } catch {
      message.error(t('notesUpdateFailed'));
    }
  };

  const removeTag = async (note: Note, targetTag: string) => {
    try {
      await updateNoteMetadata(note.id, {
        tags: (note.tags ?? []).filter((tag) => tag.toLowerCase() !== targetTag.toLowerCase()),
      });
    } catch {
      message.error(t('notesUpdateFailed'));
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

        <div className={styles.filters} aria-label="Notes filters">
          <div className={styles.filterGroup}>
            <button
              className={selectedConversationId === 'all' ? styles.filterChipActive : styles.filterChip}
              onClick={() => setSelectedConversationId('all')}
              type="button"
            >
              {t('notesAllSources')}
            </button>
            {sourceOptions.map((source) => (
              <button
                className={selectedConversationId === source.id ? styles.filterChipActive : styles.filterChip}
                key={source.id}
                onClick={() => setSelectedConversationId(source.id)}
                type="button"
              >
                {source.label}
                <span>{source.count}</span>
              </button>
            ))}
          </div>
          {tagOptions.length > 0 && (
            <div className={styles.filterGroup}>
              <button
                className={selectedTag === 'all' ? styles.filterChipActive : styles.filterChip}
                onClick={() => setSelectedTag('all')}
                type="button"
              >
                {t('notesAllTags')}
              </button>
              {tagOptions.map((tag) => (
                <button
                  className={selectedTag === tag ? styles.filterChipActive : styles.filterChip}
                  key={tag}
                  onClick={() => setSelectedTag(tag)}
                  type="button"
                >
                  <Tag size={13} />
                  {tag}
                </button>
              ))}
            </div>
          )}
        </div>

        {loading ? (
          <div className={styles.empty}>
            <Spin />
          </div>
        ) : filteredNotes.length === 0 ? (
          <div className={styles.empty}>{t('notesEmpty')}</div>
        ) : (
          <div className={styles.groupList}>
            {groupedNotes.map((group) => (
              <section className={styles.group} key={group.label}>
                <button className={styles.groupHeader} onClick={() => toggleGroup(group.label)} type="button">
                  {collapsedGroups.has(group.label) ? <ChevronRight size={17} /> : <ChevronDown size={17} />}
                  <span>{group.label}</span>
                  <strong>{group.notes.length}</strong>
                </button>
                {!collapsedGroups.has(group.label) && (
                  <div className={styles.list}>
                    {group.notes.map((note) => {
                      const isExpanded = expandedNoteIds.has(note.id);
                      const isEditingContent = editingNoteId === note.id;
                      const summary = buildNoteSummary(note.contentSnapshot);
                      const displayedContent = isExpanded ? note.contentSnapshot.trim() : summary.text;
                      return (
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
                          {isEditingContent ? (
                            <div className={styles.noteContentEditor}>
                              <textarea
                                aria-label={t('editMessage')}
                                autoFocus
                                className={styles.noteContentTextarea}
                                onChange={(event) => setContentDraft(event.target.value)}
                                onKeyDown={(event) => {
                                  if (event.key === 'Escape') {
                                    cancelContentEdit();
                                  } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                                    void saveContentEdit(note);
                                  }
                                }}
                                value={contentDraft}
                              />
                              <div className={styles.noteContentEditorActions}>
                                <button
                                  className={styles.actionButton}
                                  onClick={cancelContentEdit}
                                  type="button"
                                >
                                  {t('cancel')}
                                </button>
                                <button
                                  className={styles.actionButton}
                                  disabled={!contentDraft.trim() || contentDraft.trim() === note.contentSnapshot.trim()}
                                  onClick={() => saveContentEdit(note)}
                                  type="button"
                                >
                                  {t('save')}
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className={styles.noteBody}>
                              {renderTextWithLatinTypography(displayedContent, styles.latinText)}
                            </div>
                          )}
                          {summary.isTruncated && !isEditingContent && (
                            <button
                              className={styles.inlineButton}
                              onClick={() => toggleNoteExpansion(note.id)}
                              type="button"
                            >
                              {isExpanded ? t('notesCollapse') : t('notesExpand')}
                            </button>
                          )}
                          <div className={styles.tagEditor} aria-label={t('notesTagLabel')}>
                            {(note.tags ?? []).map((tag) => (
                              <button
                                className={styles.tagChip}
                                key={tag}
                                onClick={() => removeTag(note, tag)}
                                title={`${t('delete')} ${tag}`}
                                type="button"
                              >
                                <Tag size={12} />
                                {tag}
                                <XCircle size={12} />
                              </button>
                            ))}
                            <Input
                              className={styles.tagInput}
                              onChange={(event) => setTagDrafts((current) => ({
                                ...current,
                                [note.id]: event.target.value,
                              }))}
                              onKeyDown={(event) => {
                                if (event.key === 'Enter' || event.key === ',') {
                                  event.preventDefault();
                                  void addTag(note, tagDrafts[note.id] ?? '');
                                }
                              }}
                              placeholder={t('notesAddTagPlaceholder')}
                              value={tagDrafts[note.id] ?? ''}
                            />
                          </div>
                          <div className={styles.noteTools}>
                            <button
                              className={styles.iconActionButton}
                              aria-label={t('editMessage')}
                              onClick={() => startContentEdit(note)}
                              title={t('editMessage')}
                              type="button"
                            >
                              <Edit size={15} />
                            </button>
                            <button
                              className={styles.iconActionButton}
                              aria-label={note.isPinned ? t('notesUnpin') : t('notesPin')}
                              onClick={() => togglePinned(note)}
                              title={note.isPinned ? t('notesUnpin') : t('notesPin')}
                              type="button"
                            >
                              {note.isPinned ? <PinOff size={15} /> : <Pin size={15} />}
                            </button>
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
                      );
                    })}
                  </div>
                )}
              </section>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
