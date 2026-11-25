'use client';

/**
 * Projects panel in the main column: the project list page (image 01) and one
 * project's page (image 03: top bar, composer, recent chats, instructions and
 * memory). Scheduling and background files are intentionally left out.
 */

import React, { useMemo, useState } from 'react';
import { App, Dropdown, Input, Tooltip } from 'antd';
import { ArrowUpDown, BookText, Brain, ChevronDown, MoreHorizontal, Pin, Search } from 'lucide-react';
import type { Conversation, Project } from '@/database/schema';
import { useProjectStore } from '@/store/projects';
import { useConversationStore } from '@/store/conversation';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { ChatInput, type ChatInputProps } from '@/components/ChatInput';
import { ProjectMemoryModal } from './ProjectMemoryModal';
import { ProjectFormModal } from './ProjectFormModal';
import { useConversationMenu } from '@/components/ConversationMenu/useConversationMenu';
import { ProjectInstructionsModal } from './ProjectInstructionsModal';
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
      <ProjectFormModal open={createOpen} onClose={() => setCreateOpen(false)}
        onSubmit={async ({ name, description }) => {
          const project = await useProjectStore.getState().create(name, description);
          useProjectStore.getState().showProject(project.id);
        }} />
    </>
  );
}

function ProjectDetail({ project, onStartChat, onOpenConversation, onOpenAccountMemory, composerDisabled }:
  ProjectsPanelProps & { project: Project }) {
  const { t } = useUserPreferences();
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
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const conversationMenu = useConversationMenu({ closeMenu: () => setOpenMenuId(null) });
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);

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
              { key: 'rename', label: t('projectEditDetails') },
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
        {/* Title spans both columns so the composer and the side rows start level. */}
        <h1 className={`${styles.title} ${styles.detailTitle}`}>{project.name}</h1>
        {project.description && <p className={styles.description}>{project.description}</p>}
        <div className={styles.detailLayout}>
          <div>
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
              <ProjectChatRow key={conversation.id} conversation={conversation} menu={conversationMenu}
                open={openMenuId === conversation.id}
                onOpenChange={(open) => {
                  if (!open) conversationMenu.resetProjectQuery();
                  setOpenMenuId((current) => (open ? conversation.id : current === conversation.id ? null : current));
                }}
                onSelect={() => onOpenConversation(conversation.id)} />
            ))}
          </div>
          <aside className={styles.side}>
            <div className={styles.sideRow}>
              <BookText size={20} aria-hidden="true" />
              <span className={styles.sideLabel}>{t('projectInstructions')}</span>
              <button type="button" className={styles.linkButton} onClick={() => setInstructionsOpen(true)}>
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

      {conversationMenu.dialogs}
      <ProjectInstructionsModal project={project} open={instructionsOpen} onClose={() => setInstructionsOpen(false)} />
      <ProjectMemoryModal project={project} open={memoryOpen} onClose={() => setMemoryOpen(false)}
        onOpenAccountMemory={onOpenAccountMemory} />
      <ProjectFormModal open={renameOpen} mode="edit"
        initialValues={{ name: project.name, description: project.description ?? '' }}
        onClose={() => setRenameOpen(false)}
        onSubmit={async (values) => { await useProjectStore.getState().update(project.id, values); }} />
    </>
  );
}

/**
 * One chat in the project's recents. Hover (or an open menu) gives the row a
 * rounded highlight and swaps the time for a "⋯" button with the chat menu.
 */
function ProjectChatRow({ conversation, menu, open, onOpenChange, onSelect }: {
  conversation: Conversation;
  menu: ReturnType<typeof useConversationMenu>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: () => void;
}) {
  const { t, language } = useUserPreferences();
  const title = DEFAULT_CONVERSATION_TITLES.has(conversation.title) ? t('newChat') : conversation.title || t('newChat');
  return (
    <div className={styles.conversationRow} data-project-chat-row="" data-menu-open={open}>
      <button type="button" className={styles.conversationOpen} onClick={onSelect}>
        <span className={styles.conversationTitle}>{title}</span>
        <span className={`${styles.cardTime} ${styles.conversationTime}`}>
          {formatProjectTime(new Date(conversation.updatedAt), language)}
        </span>
      </button>
      <Dropdown
        open={open}
        onOpenChange={onOpenChange}
        trigger={['click']}
        placement="bottomRight"
        menu={{
          items: menu.itemsFor(conversation),
          onClick: ({ key, domEvent }) => {
            domEvent.stopPropagation();
            if (key === 'project-search') return; // Clicking the search field keeps the menu open.
            onOpenChange(false);
            menu.handleKey(conversation, key, title);
          },
        }}
      >
        <button type="button" className={styles.conversationMenuButton} aria-label={t('conversationMenu')}
          title={t('conversationMenu')} aria-haspopup="menu" aria-expanded={open}>
          <MoreHorizontal size={18} aria-hidden="true" />
        </button>
      </Dropdown>
    </div>
  );
}
