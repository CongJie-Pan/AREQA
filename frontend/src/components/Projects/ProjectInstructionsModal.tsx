'use client';

/**
 * "設定專案指示" dialog (temp/新增指示的頁面要像這樣.jpg): a title, one line on what
 * the instructions do, a large text area, and 取消 / 儲存指示. Saving stays
 * disabled until the text changes.
 */

import React, { useEffect, useRef, useState } from 'react';
import { App, Modal } from 'antd';
import type { Project } from '@/database/schema';
import { useProjectStore } from '@/store/projects';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { MAX_PROJECT_INSTRUCTIONS_CHARS } from '@/services/projects';
import styles from './Projects.module.css';

export interface ProjectInstructionsModalProps {
  project: Project;
  open: boolean;
  onClose: () => void;
}

export function ProjectInstructionsModal({ project, open, onClose }: ProjectInstructionsModalProps) {
  const { t } = useUserPreferences();
  const { message } = App.useApp();
  const [draft, setDraft] = useState(project.instructions);
  const [saving, setSaving] = useState(false);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) setDraft(project.instructions);
  }, [open, project.instructions]);

  const unchanged = draft.trim() === project.instructions.trim();
  const save = async () => {
    if (unchanged || saving) return;
    setSaving(true);
    try {
      await useProjectStore.getState().update(project.id, { instructions: draft.trim() });
      onClose();
    } catch {
      message.error(t('projectSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      closable={false}
      width={900}
      destroyOnHidden
      className={styles.formModal}
      title={t('projectInstructionsTitle')}
      // The dialog takes focus when it opens; hand it to the text area so typing starts there.
      afterOpenChange={(visible) => { if (visible) areaRef.current?.focus(); }}
      footer={(
        <div className={styles.formFooter}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>{t('cancel')}</button>
          <button type="button" className={styles.primaryButton} disabled={unchanged || saving}
            onClick={() => { void save(); }}>
            {t('projectInstructionsSave')}
          </button>
        </div>
      )}
    >
      <p className={styles.instructionsIntro}>{t('projectInstructionsIntro', { name: project.name })}</p>
      <textarea
        ref={areaRef}
        autoFocus
        className={styles.instructionsArea}
        value={draft}
        maxLength={MAX_PROJECT_INSTRUCTIONS_CHARS}
        placeholder={t('projectInstructionsPlaceholder')}
        aria-label={t('projectInstructions')}
        onChange={(event) => setDraft(event.target.value)}
      />
    </Modal>
  );
}
