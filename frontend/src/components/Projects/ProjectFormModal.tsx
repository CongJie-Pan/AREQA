'use client';

/**
 * Create / edit project dialog (temp/當我按sidebar專案的時候_加號後_顯示這個視窗_要是這個樣子.jpg):
 * "您正在進行什麼工作？" names the project, "您想達成什麼目標？" records its goal.
 * The reference's "背景資訊" section is intentionally left out.
 */

import React, { useEffect, useRef, useState } from 'react';
import type { InputRef } from 'antd';
import { App, Input, Modal } from 'antd';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { MAX_PROJECT_DESCRIPTION_CHARS, MAX_PROJECT_NAME_CHARS } from '@/services/projects';
import styles from './Projects.module.css';

export interface ProjectFormValues {
  name: string;
  description: string;
}

export interface ProjectFormModalProps {
  open: boolean;
  mode?: 'create' | 'edit';
  initialValues?: Partial<ProjectFormValues>;
  onClose: () => void;
  onSubmit: (values: ProjectFormValues) => Promise<void>;
}

export function ProjectFormModal({ open, mode = 'create', initialValues, onClose, onSubmit }: ProjectFormModalProps) {
  const { t } = useUserPreferences();
  const { message } = App.useApp();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const nameRef = useRef<InputRef>(null);
  const initialName = initialValues?.name ?? '';
  const initialDescription = initialValues?.description ?? '';

  // Reset as soon as the dialog opens, not after its animation, so early typing is kept.
  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setDescription(initialDescription);
  }, [initialDescription, initialName, open]);

  const submit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await onSubmit({ name: name.trim(), description: description.trim() });
      onClose();
    } catch {
      message.error(t('projectSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const title = t(mode === 'create' ? 'projectCreate' : 'projectEditTitle');
  return (
    <Modal
      open={open}
      title={title}
      onCancel={onClose}
      width={640}
      destroyOnHidden
      className={styles.formModal}
      // The dialog takes focus when it opens; hand it to the name field so typing starts there.
      afterOpenChange={(visible) => { if (visible) nameRef.current?.focus(); }}
      footer={(
        <div className={styles.formFooter}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>{t('cancel')}</button>
          <button type="button" className={styles.primaryButton} disabled={!name.trim() || saving}
            onClick={() => { void submit(); }}>
            {mode === 'create' ? t('projectCreate') : t('save')}
          </button>
        </div>
      )}
    >
      <form className={styles.form} onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <label className={styles.formField}>
          <span className={styles.formLabel}>{t('projectNameLabel')}</span>
          <Input
            ref={nameRef}
            autoFocus
            variant="filled"
            maxLength={MAX_PROJECT_NAME_CHARS}
            value={name}
            placeholder={t('projectNamePlaceholder')}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className={styles.formField}>
          <span className={styles.formLabel}>{t('projectGoalLabel')}</span>
          <Input.TextArea
            variant="filled"
            maxLength={MAX_PROJECT_DESCRIPTION_CHARS}
            value={description}
            rows={4}
            placeholder={t('projectGoalPlaceholder')}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        {/* Enter in the name field submits; the textarea keeps Enter for new lines. */}
        <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
      </form>
    </Modal>
  );
}
