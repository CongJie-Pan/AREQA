'use client';

/**
 * Project memory dialog: the memory profile row (view, edit, delete), the
 * account-memory toggle, and a detail view where the learner can ask AREQA to
 * change the profile in plain words.
 */

import React, { useEffect, useRef, useState } from 'react';
import { App, Button, Input, Modal, Popconfirm, Switch, Tooltip } from 'antd';
import { ArrowLeft, Pencil, RefreshCw, Trash2 } from 'lucide-react';
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
  const latestChatAt = useConversationStore((state) => state.conversations
    .filter((conversation) => conversation.projectId === project.id)
    .reduce<number | null>((latest, conversation) => Math.max(latest ?? 0, new Date(conversation.updatedAt).getTime()), null));
  const autoRefreshedRef = useRef(false);
  const updatedAgo = formatProjectTime(project.memoryUpdatedAt, language);

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
      .catch(() => undefined) // Silent: the learner can still press Update and see the error.
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

  const deleteButton = (children: React.ReactNode) => (
    <Popconfirm title={t('projectMemoryDeleteConfirm')} onConfirm={() => { void remove(); }} okText={t('delete')}>
      {children}
    </Popconfirm>
  );

  return (
    <Modal
      open={open}
      onCancel={close}
      footer={null}
      width={680}
      destroyOnHidden
      title={view === 'detail' ? (
        <button type="button" className={styles.breadcrumbLink} onClick={() => setView('overview')}>
          <ArrowLeft size={16} style={{ verticalAlign: '-3px', marginRight: 6 }} aria-hidden="true" />
          {t('projectMemory')}
        </button>
      ) : t('projectMemory')}
    >
      {view === 'overview' ? (
        <>
          {hasMemory ? (
            <div className={styles.memoryRow}>
              <button type="button" className={styles.linkButton} onClick={() => setView('detail')}>
                {t('projectMemoryProfile')}
              </button>
              <span className={`${styles.ellipsis} ${styles.muted}`}>{project.memorySummary}</span>
              <span className={styles.muted}>{updatedAgo && t('projectMemoryUpdated', { time: updatedAgo })}</span>
              <span>
                <Tooltip title={t('projectEdit')}>
                  <Button type="text" size="small" icon={<Pencil size={15} />} aria-label={t('projectEdit')}
                    onClick={() => setView('detail')} />
                </Tooltip>
                {deleteButton(
                  <Button type="text" size="small" icon={<Trash2 size={15} />} aria-label={t('delete')} />,
                )}
              </span>
            </div>
          ) : (
            <p className={styles.muted}>{t('projectMemoryEmpty')}</p>
          )}
          <div style={{ padding: '4px 12px 12px' }}>
            <Button size="small" icon={<RefreshCw size={14} />} loading={busy === 'refresh'} onClick={() => { void refresh(); }}>
              {t('projectMemoryRefresh')}
            </Button>
          </div>
          <div className={styles.memoryToggleRow}>
            <div>
              <div>{t('projectUseAccountMemory')}</div>
              <div className={styles.muted}>{t('projectUseAccountMemoryHint')}</div>
              <button type="button" className={styles.linkButton} style={{ textDecoration: 'underline', marginTop: 4 }}
                onClick={() => { close(); onOpenAccountMemory(); }}>
                {t('projectViewAccountMemory')}
              </button>
            </div>
            <Switch checked={project.useAccountMemory} aria-label={t('projectUseAccountMemory')}
              onChange={(checked) => { void toggleAccountMemory(checked); }} />
          </div>
        </>
      ) : (
        <div>
          <div className={styles.header} style={{ marginBottom: 8 }}>
            <strong style={{ fontSize: 17 }}>{t('projectMemoryProfile')}</strong>
            {deleteButton(<Button size="small">{t('delete')}</Button>)}
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
            <Input
              value={instruction}
              maxLength={1000}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder={t('projectMemoryRevisePlaceholder')}
              aria-label={t('projectMemoryRevisePlaceholder')}
              disabled={busy === 'revise'}
            />
            <Button type="primary" htmlType="submit" loading={busy === 'revise'} disabled={!instruction.trim()}>
              {t('save')}
            </Button>
          </form>
        </div>
      )}
    </Modal>
  );
}
