'use client';

/**
 * Project memory dialog (images 04–06).
 *
 * Overview: one "Profile" row (summary, "updated …"; Edit and Delete appear on
 * hover) and the account-memory switch. Detail: last updated, summary, detail
 * bullets, Delete, and a "Tell AREQA what to change" field that rewrites the
 * profile. Opening the dialog refreshes a stale profile from the project chats.
 */

import React, { useEffect, useRef, useState } from 'react';
import { App, Button, Modal, Popconfirm, Spin, Switch, Tooltip } from 'antd';
import { ArrowLeft, ArrowUp, Pencil, Trash2 } from 'lucide-react';
import type { Project } from '@/database/schema';
import { useProjectStore } from '@/store/projects';
import { useConversationStore } from '@/store/conversation';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { formatProjectTime } from './format';
import styles from './Projects.module.css';

/** Auto-refresh at most this often, so opening the dialog repeatedly does not re-run the model. */
const AUTO_REFRESH_MIN_AGE_MS = 60 * 60 * 1000;

/** Memory is stale when a project chat changed after it was written (and it is old enough). */
export function isProjectMemoryStale(memoryUpdatedAt: Date | null, latestChatAt: number | null, now = Date.now()): boolean {
  if (latestChatAt === null) return false;
  if (!memoryUpdatedAt) return true;
  return latestChatAt > memoryUpdatedAt.getTime() && now - memoryUpdatedAt.getTime() >= AUTO_REFRESH_MIN_AGE_MS;
}

export interface ProjectMemoryModalProps {
  project: Project;
  open: boolean;
  onClose: () => void;
  onOpenAccountMemory: () => void;
}

export function ProjectMemoryModal({ project, open, onClose, onOpenAccountMemory }: ProjectMemoryModalProps) {
  const { message } = App.useApp();
  const { t, language } = useUserPreferences();
  const [view, setView] = useState<'overview' | 'detail'>('overview');
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState<'refresh' | 'revise' | null>(null);
  const hasMemory = Boolean(project.memorySummary || project.memoryDetails.length);
  const updatedAgo = formatProjectTime(project.memoryUpdatedAt, language);
  const latestChatAt = useConversationStore((state) => state.conversations
    .filter((conversation) => conversation.projectId === project.id)
    .reduce<number | null>((latest, conversation) => Math.max(latest ?? 0, new Date(conversation.updatedAt).getTime()), null));
  const autoRefreshedRef = useRef(false);

  const close = () => {
    setView('overview');
    setInstruction('');
    onClose();
  };

  const refresh = async () => {
    setBusy('refresh');
    try {
      const refreshed = await useProjectStore.getState().refreshMemory(project.id);
      if (!refreshed) message.info(t('projectMemoryNothingToLearn'));
    } catch {
      message.error(t('projectMemoryRefreshFailed'));
    } finally {
      setBusy(null);
    }
  };

  // Opening the dialog brings memory up to date with newer project chats, once per mount.
  useEffect(() => {
    if (!open || autoRefreshedRef.current || busy) return;
    if (!isProjectMemoryStale(project.memoryUpdatedAt, latestChatAt)) return;
    autoRefreshedRef.current = true;
    setBusy('refresh');
    useProjectStore.getState().refreshMemory(project.id)
      .catch(() => undefined) // Silent: the empty state still offers a manual update.
      .finally(() => setBusy(null));
  }, [busy, latestChatAt, open, project.id, project.memoryUpdatedAt]);

  const revise = async () => {
    const text = instruction.trim();
    if (!text) return;
    setBusy('revise');
    try {
      await useProjectStore.getState().reviseMemory(project.id, text);
      setInstruction('');
    } catch {
      message.error(t('projectMemoryRefreshFailed'));
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    try {
      await useProjectStore.getState().clearMemory(project.id);
      setView('overview');
    } catch {
      message.error(t('projectSaveFailed'));
    }
  };

  const toggleAccountMemory = async (checked: boolean) => {
    try {
      await useProjectStore.getState().update(project.id, { useAccountMemory: checked });
    } catch {
      message.error(t('projectSaveFailed'));
    }
  };

  const withDeleteConfirm = (children: React.ReactElement) => (
    <Popconfirm title={t('projectMemoryDeleteConfirm')} onConfirm={() => { void remove(); }} okText={t('delete')}
      okButtonProps={{ danger: true }}>
      {children}
    </Popconfirm>
  );

  return (
    <Modal
      open={open}
      onCancel={close}
      footer={null}
      width={900}
      centered
      destroyOnHidden
      className={styles.memoryModal}
      title={view === 'detail' ? (
        <button type="button" className={styles.memoryBack} onClick={() => setView('overview')}>
          <ArrowLeft size={18} aria-hidden="true" />
          <span>{t('projectMemory')}</span>
        </button>
      ) : t('projectMemory')}
    >
      {view === 'overview' ? (
        <>
          {hasMemory ? (
            <div className={styles.memoryRow} role="group" aria-label={t('projectMemoryProfile')}>
              <button type="button" className={styles.memoryRowOpen} onClick={() => setView('detail')}>
                <span className={styles.memoryRowLabel}>{t('projectMemoryProfile')}</span>
                <span className={`${styles.ellipsis} ${styles.memoryRowSummary}`}>{project.memorySummary}</span>
                <span className={styles.memoryRowTime}>
                  {busy === 'refresh' ? <Spin size="small" /> : updatedAgo && t('projectMemoryUpdated', { time: updatedAgo })}
                </span>
              </button>
              <span className={styles.memoryRowActions}>
                <Tooltip title={t('projectMemoryEditTooltip')}>
                  <button type="button" className={styles.iconButton} aria-label={t('projectEdit')}
                    onClick={() => setView('detail')}>
                    <Pencil size={17} aria-hidden="true" />
                  </button>
                </Tooltip>
                {withDeleteConfirm(
                  <button type="button" className={styles.iconButton} aria-label={t('delete')}>
                    <Trash2 size={17} aria-hidden="true" />
                  </button>,
                )}
              </span>
            </div>
          ) : (
            <div className={styles.memoryEmpty}>
              <span className={styles.muted}>{t('projectMemoryEmpty')}</span>
              <Button size="small" loading={busy === 'refresh'} onClick={() => { void refresh(); }}>
                {t('projectMemoryRefresh')}
              </Button>
            </div>
          )}
          <div className={styles.memoryToggleRow}>
            <div>
              <div className={styles.memoryToggleTitle}>{t('projectUseAccountMemory')}</div>
              <div className={styles.memoryToggleHint}>{t('projectUseAccountMemoryHint')}</div>
              <button type="button" className={styles.underlineLink}
                onClick={() => { close(); onOpenAccountMemory(); }}>
                {t('projectViewAccountMemory')}
              </button>
            </div>
            <Switch checked={project.useAccountMemory} aria-label={t('projectUseAccountMemory')}
              onChange={(checked) => { void toggleAccountMemory(checked); }} />
          </div>
        </>
      ) : (
        <div className={styles.memoryDetailBody}>
          <div className={styles.memoryDetailHeader}>
            <h3>{t('projectMemoryProfile')}</h3>
            {withDeleteConfirm(<button type="button" className={styles.secondaryButton}>{t('delete')}</button>)}
          </div>
          <dl className={styles.memoryDetail}>
            <dt>{t('projectMemoryLastUpdated')}</dt>
            <dd>{project.memoryUpdatedAt
              ? new Intl.DateTimeFormat(language, { dateStyle: 'medium' }).format(project.memoryUpdatedAt) : '—'}</dd>
            <dt>{t('projectMemorySummary')}</dt>
            <dd>{project.memorySummary || '—'}</dd>
            {project.memoryDetails.length > 0 && (
              <>
                <dt>{t('projectMemoryDetails')}</dt>
                <dd><ul>{project.memoryDetails.map((detail, index) => <li key={index}>{detail}</li>)}</ul></dd>
              </>
            )}
          </dl>
          <form className={styles.reviseForm} onSubmit={(event) => { event.preventDefault(); void revise(); }}>
            <input
              className={styles.reviseInput}
              value={instruction}
              maxLength={1000}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder={t('projectMemoryRevisePlaceholder')}
              aria-label={t('projectMemoryRevisePlaceholder')}
              disabled={busy === 'revise'}
            />
            <button type="submit" className={styles.reviseSend} aria-label={t('save')}
              disabled={!instruction.trim() || busy === 'revise'}>
              {busy === 'revise' ? <Spin size="small" /> : <ArrowUp size={18} aria-hidden="true" />}
            </button>
          </form>
        </div>
      )}
    </Modal>
  );
}
