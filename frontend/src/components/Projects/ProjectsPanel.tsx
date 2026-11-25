'use client';

/**
 * Projects panel in the main column: the project list page (image 01) and one
 * project's page (image 03: top bar, composer, recent chats, instructions and
 * memory). Scheduling and background files are intentionally left out.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { App, Dropdown, Input, Modal, Tooltip } from 'antd';
import { ArrowUpDown, BookText, Brain, ChevronDown, Pin, Search } from 'lucide-react';
import type { Conversation, Project } from '@/database/schema';
import { useProjectStore } from '@/store/projects';
import { useConversationStore } from '@/store/conversation';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { ChatInput, type ChatInputProps } from '@/components/ChatInput';
import { MAX_PROJECT_INSTRUCTIONS_CHARS, MAX_PROJECT_NAME_CHARS } from '@/services/projects';
import { ProjectMemoryModal } from './ProjectMemoryModal';
import { ProjectIcon } from './ProjectIcon';
import { formatProjectTime } from './format';
import styles from './Projects.module.css';

const DEFAULT_CONVERSATION_TITLES = new Set(['新對話', '新对话']);

export interface ProjectsPanelProps {
  /** Send the first message of a new conversation in the open project. */
  onStartChat: ChatInputProps['onSend'];
  onOpenConversation: (conversationId: string) => void;
  onOpenAccountMemory: () => void;
  /** Composer is busy (another reply is streaming). */
  composerDisabled?: boolean;
}

/** Ask for a project name; used for create and rename. */
export function ProjectNameModal({ open, initialName = '', title, onClose, onSubmit }: {
  open: boolean;
  initialName?: string;
  title: string;
  onClose: () => void;
  onSubmit: (name: string) => Promise<void>;
}) {
  const { t } = useUserPreferences();
  const { message } = App.useApp();
  const [name, setName] = useState(initialName);
  const [saving, setSaving] = useState(false);
  // Reset as soon as the dialog opens, not after its animation, so early typing is kept.
  useEffect(() => {
    if (open) setName(initialName);
  }, [initialName, open]);
  const submit = async () => {
    if (!name.trim()) {
      message.warning(t('projectNameRequired'));
      return;
    }
    setSaving(true);
    try {
      await onSubmit(name.trim());
      onClose();
    } catch {
      message.error(t('projectSaveFailed'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal open={open} title={title} onCancel={onClose} onOk={() => { void submit(); }} okText={t('save')}
      confirmLoading={saving} okButtonProps={{ disabled: !name.trim() }} destroyOnHidden>
      <Input autoFocus maxLength={MAX_PROJECT_NAME_CHARS} value={name} placeholder={t('projectNamePlaceholder')}
        aria-label={t('projectNamePlaceholder')}
        onChange={(event) => setName(event.target.value)} onPressEnter={() => { void submit(); }} />
    </Modal>
  );
}

export function ProjectsPanel(props: ProjectsPanelProps) {
  const view = useProjectStore((state) => state.view);
  const project = useProjectStore((state) => (
    view.kind === 'project' ? state.projects.find((item) => item.id === view.projectId) : undefined
  ));
  return (
    <div className={styles.page}>
      {project ? <ProjectDetail project={project} {...props} /> : <div className={styles.inner}><ProjectList /></div>}
    </div>
  );
}

function ProjectList() {
  const { t, language } = useUserPreferences();
  const { message } = App.useApp();
  const projects = useProjectStore((state) => state.projects);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [sortByName, setSortByName] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const filtered = projects.filter((project) => !needle || project.name.toLocaleLowerCase().includes(needle));
    return filtered.sort((a, b) => (Number(b.isPinned) - Number(a.isPinned))
      || (sortByName ? a.name.localeCompare(b.name, language) : b.updatedAt.getTime() - a.updatedAt.getTime()));
  }, [language, projects, query, sortByName]);

  const togglePin = async (project: Project) => {
    try {
      await useProjectStore.getState().update(project.id, { isPinned: !project.isPinned });
    } catch {
      message.error(t('projectSaveFailed'));
    }
  };

  return (
    <>
      <div className={styles.header}>
        <h1 className={styles.title}>{t('projects')}</h1>
        <div className={styles.headerActions}>
          <Tooltip title={t('projectSearchPlaceholder')}>
            <button type="button" className={styles.iconButton} aria-label={t('projectSearchPlaceholder')}
              aria-pressed={searchOpen} onClick={() => setSearchOpen((open) => !open)}>
              <Search size={19} aria-hidden="true" />
            </button>
          </Tooltip>
          <Tooltip title={t(sortByName ? 'projectSortName' : 'projectSortRecent')}>
            <button type="button" className={styles.iconButton} aria-pressed={sortByName}
              aria-label={t(sortByName ? 'projectSortName' : 'projectSortRecent')}
              onClick={() => setSortByName((value) => !value)}>
              <ArrowUpDown size={19} aria-hidden="true" />
            </button>
          </Tooltip>
          <button type="button" className={styles.primaryButton} onClick={() => setCreateOpen(true)}>
            {t('projectNew')}
          </button>
        </div>
      </div>
      {searchOpen && (
        <Input autoFocus allowClear className={styles.search} prefix={<Search size={16} aria-hidden="true" />}
          placeholder={t('projectSearchPlaceholder')} aria-label={t('projectSearchPlaceholder')}
          value={query} onChange={(event) => setQuery(event.target.value)} />
      )}
      {visible.length === 0 ? (
        <p className={styles.empty}>{t('projectsEmpty')}</p>
      ) : (
        <div className={styles.grid}>
          {visible.map((project) => (
            <div key={project.id} role="button" tabIndex={0} className={styles.card}
              onClick={() => useProjectStore.getState().showProject(project.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  useProjectStore.getState().showProject(project.id);
                }
              }}>
              <span className={styles.cardIcon}><ProjectIcon size={20} /></span>
              <span className={styles.cardText}>
                <span className={styles.cardName}>{project.name}</span>
                <span className={styles.cardTime}>{formatProjectTime(project.updatedAt, language)}</span>
              </span>
              {/* Pinned projects always show a filled pin; others reveal an outline pin on hover. */}
              <Tooltip title={t(project.isPinned ? 'projectUnpin' : 'projectPin')}>
                <button type="button" className={`${styles.iconButton} ${styles.cardPin}`}
                  aria-pressed={project.isPinned} aria-label={t(project.isPinned ? 'projectUnpin' : 'projectPin')}
                  onClick={(event) => { event.stopPropagation(); void togglePin(project); }}>
                  <Pin size={18} aria-hidden="true" fill={project.isPinned ? 'currentColor' : 'none'} />
                </button>
              </Tooltip>
            </div>
          ))}
        </div>
      )}
      <ProjectNameModal open={createOpen} title={t('projectCreate')} onClose={() => setCreateOpen(false)}
        onSubmit={async (name) => {
          const project = await useProjectStore.getState().create(name);
          useProjectStore.getState().showProject(project.id);
        }} />
    </>
  );
}

function ProjectDetail({ project, onStartChat, onOpenConversation, onOpenAccountMemory, composerDisabled }:
  ProjectsPanelProps & { project: Project }) {
  const { t, language } = useUserPreferences();
  const { message, modal } = App.useApp();
  const allConversations = useConversationStore((state) => state.conversations);
  const [chatQuery, setChatQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const conversations = useMemo(() => {
    const needle = chatQuery.trim().toLocaleLowerCase();
    return allConversations
      .filter((conversation: Conversation) => conversation.projectId === project.id
        && (!needle || conversation.title.toLocaleLowerCase().includes(needle)))
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  }, [allConversations, chatQuery, project.id]);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [instructionsDraft, setInstructionsDraft] = useState(project.instructions);
  const [savingInstructions, setSavingInstructions] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);

  const saveInstructions = async () => {
    setSavingInstructions(true);
    try {
      await useProjectStore.getState().update(project.id, { instructions: instructionsDraft.trim() });
      setInstructionsOpen(false);
    } catch {
      message.error(t('projectSaveFailed'));
    } finally {
      setSavingInstructions(false);
    }
  };

  const togglePin = async () => {
    try {
      await useProjectStore.getState().update(project.id, { isPinned: !project.isPinned });
    } catch {
      message.error(t('projectSaveFailed'));
    }
  };

  const confirmDelete = () => {
    modal.confirm({
      title: t('projectDeleteConfirm', { name: project.name }),
      okText: t('delete'),
      okButtonProps: { danger: true },
      onOk: () => useProjectStore.getState().remove(project.id),
    });
  };

  return (
    <>
      {/* Top bar: "專案 / Diary ▾" on the left, search and pin on the right (image 03). */}
      <header className={styles.topBar}>
        <nav className={styles.breadcrumb} aria-label={t('projects')}>
          <button type="button" className={styles.breadcrumbLink} onClick={() => useProjectStore.getState().showList()}>
            {t('projects')}
          </button>
          <span className={styles.breadcrumbSeparator} aria-hidden="true">/</span>
          <Dropdown trigger={['click']} menu={{
            items: [
              { key: 'rename', label: t('rename') },
              { key: 'pin', label: t(project.isPinned ? 'projectUnpin' : 'projectPin') },
              { type: 'divider' },
              { key: 'delete', danger: true, label: t('delete') },
            ],
            onClick: ({ key }) => {
              if (key === 'rename') setRenameOpen(true);
              else if (key === 'pin') void togglePin();
              else if (key === 'delete') confirmDelete();
            },
          }}>
            <button type="button" className={styles.breadcrumbCurrent}>
              <span>{project.name}</span>
              <ChevronDown size={16} aria-hidden="true" />
            </button>
          </Dropdown>
        </nav>
        <div className={styles.headerActions}>
          <Tooltip title={t('projectSearchChats')}>
            <button type="button" className={styles.iconButton} aria-label={t('projectSearchChats')}
              aria-pressed={searchOpen} onClick={() => setSearchOpen((open) => !open)}>
              <Search size={19} aria-hidden="true" />
            </button>
          </Tooltip>
          <Tooltip title={t(project.isPinned ? 'projectUnpin' : 'projectPin')}>
            <button type="button" className={styles.iconButton} aria-label={t(project.isPinned ? 'projectUnpin' : 'projectPin')}
              aria-pressed={project.isPinned} onClick={() => { void togglePin(); }}>
              <Pin size={19} aria-hidden="true" fill={project.isPinned ? 'currentColor' : 'none'} />
            </button>
          </Tooltip>
        </div>
      </header>

      <div className={styles.inner}>
        <div className={styles.detailLayout}>
          <div>
            <h1 className={`${styles.title} ${styles.detailTitle}`}>{project.name}</h1>
            <div className={styles.composer}>
              <ChatInput
                key={project.id}
                onSend={onStartChat}
                disabled={composerDisabled}
                placeholder={t('projectNewSession', { name: project.name })}
              />
            </div>
            {searchOpen && (
              <Input autoFocus allowClear className={styles.search} prefix={<Search size={16} aria-hidden="true" />}
                placeholder={t('projectSearchChats')} aria-label={t('projectSearchChats')}
                value={chatQuery} onChange={(event) => setChatQuery(event.target.value)} />
            )}
            <h2 className={styles.sectionTitle}>{t('projectRecents')}</h2>
            {conversations.length === 0 ? (
              <p className={styles.muted}>{t('projectNoConversations')}</p>
            ) : conversations.map((conversation) => (
              <button key={conversation.id} type="button" className={styles.conversationRow}
                data-project-chat-row=""
                onClick={() => onOpenConversation(conversation.id)}>
                <span className={styles.conversationTitle}>
                  {DEFAULT_CONVERSATION_TITLES.has(conversation.title) ? t('newChat') : conversation.title || t('newChat')}
                </span>
                <span className={styles.cardTime}>{formatProjectTime(new Date(conversation.updatedAt), language)}</span>
              </button>
            ))}
          </div>
          <aside className={styles.side}>
            <div className={styles.sideRow}>
              <BookText size={20} aria-hidden="true" />
              <span className={styles.sideLabel}>{t('projectInstructions')}</span>
              <button type="button" className={styles.linkButton} onClick={() => {
                setInstructionsDraft(project.instructions);
                setInstructionsOpen(true);
              }}>
                {t(project.instructions ? 'projectEdit' : 'projectAdd')}
              </button>
            </div>
            {project.instructions && <p className={styles.instructionsPreview}>{project.instructions}</p>}
            <div className={styles.sideRow}>
              <Brain size={20} aria-hidden="true" />
              <span className={styles.sideLabel}>{t('projectMemory')}</span>
              <button type="button" className={styles.linkButton} onClick={() => setMemoryOpen(true)}>
                {t('projectView')}
              </button>
            </div>
            <p className={styles.visibility}>{t('projectPrivate')}</p>
          </aside>
        </div>
      </div>

      <Modal open={instructionsOpen} title={t('projectInstructions')} onCancel={() => setInstructionsOpen(false)}
        onOk={() => { void saveInstructions(); }} okText={t('save')} confirmLoading={savingInstructions} destroyOnHidden>
        <p className={styles.muted}>{t('projectInstructionsHint')}</p>
        <Input.TextArea autoFocus value={instructionsDraft} maxLength={MAX_PROJECT_INSTRUCTIONS_CHARS} showCount
          autoSize={{ minRows: 6, maxRows: 16 }} placeholder={t('projectInstructionsPlaceholder')}
          aria-label={t('projectInstructions')} onChange={(event) => setInstructionsDraft(event.target.value)} />
      </Modal>
      <ProjectMemoryModal project={project} open={memoryOpen} onClose={() => setMemoryOpen(false)}
        onOpenAccountMemory={onOpenAccountMemory} />
      <ProjectNameModal open={renameOpen} initialName={project.name} title={t('rename')}
        onClose={() => setRenameOpen(false)}
        onSubmit={async (name) => { await useProjectStore.getState().update(project.id, { name }); }} />
    </>
  );
}
