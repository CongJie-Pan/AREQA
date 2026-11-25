'use client';

/** "Add to project": search existing projects or create one from the typed name. */

import React, { useMemo, useState } from 'react';
import { Input, Modal } from 'antd';
import { FolderClosed, Plus, Search } from 'lucide-react';
import { useProjectStore } from '@/store/projects';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { MAX_PROJECT_NAME_CHARS } from '@/services/projects';
import styles from './Projects.module.css';

export interface ProjectPickerModalProps {
  open: boolean;
  /** Project the conversation is already in; it is not offered again. */
  currentProjectId?: string | null;
  onClose: () => void;
  onPick: (projectId: string) => void | Promise<void>;
}

export function ProjectPickerModal({ open, currentProjectId, onClose, onPick }: ProjectPickerModalProps) {
  const { t } = useUserPreferences();
  const projects = useProjectStore((state) => state.projects);
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const trimmed = query.trim();
  const matches = useMemo(() => {
    const needle = trimmed.toLocaleLowerCase();
    return projects.filter((project) => project.id !== currentProjectId
      && (!needle || project.name.toLocaleLowerCase().includes(needle)));
  }, [currentProjectId, projects, trimmed]);
  const exactMatch = projects.some((project) => project.name.toLocaleLowerCase() === trimmed.toLocaleLowerCase());

  const close = () => {
    setQuery('');
    onClose();
  };

  const createAndPick = async () => {
    if (!trimmed || creating) return;
    setCreating(true);
    try {
      const project = await useProjectStore.getState().create(trimmed);
      await onPick(project.id);
      close();
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal open={open} onCancel={close} footer={null} title={t('projectAddTo')} destroyOnHidden>
      <Input
        autoFocus
        allowClear
        maxLength={MAX_PROJECT_NAME_CHARS}
        prefix={<Search size={16} aria-hidden="true" />}
        placeholder={t('projectSearchOrCreate')}
        aria-label={t('projectSearchOrCreate')}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onPressEnter={() => {
          if (matches.length === 1 && trimmed) void Promise.resolve(onPick(matches[0].id)).then(close);
          else if (!exactMatch) void createAndPick();
        }}
      />
      <div className={styles.pickerList} role="listbox" aria-label={t('projects')}>
        <button
          type="button"
          className={styles.pickerItem}
          disabled={creating}
          onClick={() => { void (trimmed && !exactMatch ? createAndPick() : null); }}
          aria-disabled={!trimmed || exactMatch}
          style={!trimmed || exactMatch ? { opacity: 0.5, cursor: 'default' } : undefined}
        >
          <Plus size={16} aria-hidden="true" />
          <span>{trimmed && !exactMatch ? t('projectCreateNamed', { name: trimmed }) : t('projectNew')}</span>
        </button>
        {matches.map((project) => (
          <button
            key={project.id}
            type="button"
            role="option"
            aria-selected={false}
            className={styles.pickerItem}
            onClick={() => { void Promise.resolve(onPick(project.id)).then(close); }}
          >
            <FolderClosed size={16} aria-hidden="true" />
            <span className={styles.ellipsis}>{project.name}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}
