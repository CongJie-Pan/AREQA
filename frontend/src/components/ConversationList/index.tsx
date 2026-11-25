'use client';

/**
 * ConversationList Component
 * Sidebar displaying conversation history grouped by time
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { App, Dropdown, Input, Modal, Spin, Tooltip } from 'antd';
import { MessageCircle, MoreHorizontal, Pencil, PinOff, Plus, Search, ChevronRight, Trash2, PanelLeftClose, Mail as MailIcon } from 'lucide-react';
import { BranchIcon, conversationBranchesEnabled } from '@/components/ConversationBranch/BranchIcon';
import { useConversationStore } from '@/store/conversation';
import { useChatStore } from '@/store/chat';
import { useMailboxStore } from '@/store/mailbox';
import { useFeatureStore } from '@/store/features';
import { SidePanelType } from '@/types/panel';
import {
  logConversationHistoryDebugEvent,
  switchConversation,
} from '@/services/chat';
import { UserAuthUI } from '../Auth';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';
import { conversationKindOf } from '@/utils/conversationKind';
import { WorkspaceSwitch } from '@/components/WorkspaceSwitch';
import { menuLabel, useConversationMenu } from '@/components/ConversationMenu/useConversationMenu';
import { usePinnedConversationStore } from '@/store/pinnedConversations';
import { ProjectFormModal, ProjectIcon } from '@/components/Projects';
import { useProjectStore } from '@/store/projects';
import type { Conversation, Project } from '@/database/schema';
import { useAuthStore } from '@/store/auth';

const LONG_PRESS_MENU_MS = 520;
const DEFAULT_CONVERSATION_TITLES = new Set(['新對話', '新对话']);
/** Conversations listed under a pinned project before "View all". */
const PINNED_PROJECT_PREVIEW_COUNT = 3;

export interface ConversationListProps {
  /** Callback when conversation is selected */
  onSelect?: (conversationId: string) => void;
  /** Callback when new conversation is created */
  onNew?: () => void;
  /** Callback when conversation is deleted */
  onDelete?: (conversationId: string) => void;
  /** Callback to toggle sidebar visibility */
  onToggleSidebar?: () => void;
  /** Whether the shell provides the persistent sidebar toggle. */
  externalSidebarToggle?: boolean;
  /** Callback to open GUM panel */
  onSelectGumPanel?: (type: Exclude<SidePanelType, null>) => void;
  /** Class name for styling */
  className?: string;
  /** The Projects list page is showing (highlights the Projects entry). */
  projectsActive?: boolean;
  /** Project whose page is showing (highlights its pinned row). */
  activeProjectId?: string | null;
}

/**
 * ConversationList displays all conversations in sidebar
 */
export function ConversationList({
  onSelect,
  onNew,
  onDelete,
  onToggleSidebar,
  externalSidebarToggle = false,
  onSelectGumPanel,
  className,
  projectsActive = false,
  activeProjectId = null,
}: ConversationListProps) {
  const { modal } = App.useApp();
  const { resolvedTheme, t } = useUserPreferences();
  const longPressTimerRef = useRef<number | null>(null);
  const longPressTriggeredRef = useRef(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  /** null until the learner toggles the group; until then it follows whether pinned projects exist. */
  const [pinnedOpenChoice, setPinnedOpen] = useState<boolean | null>(null);
  const [recentsOpen, setRecentsOpen] = useState(true);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [projectMenuId, setProjectMenuId] = useState<string | null>(null);
  const [renameProjectId, setRenameProjectId] = useState<string | null>(null);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const isSignedIn = useAuthStore((state) => Boolean(state.user));
  const projects = useProjectStore((state) => state.projects);
  const pinnedProjects = useMemo(() => projects.filter((project) => project.isPinned), [projects]);
  const hasPinnedProjects = isSignedIn && pinnedProjects.length > 0;
  // Pinned projects live in the Pinned group, so it starts open when there are any.
  const pinnedOpen = pinnedOpenChoice ?? hasPinnedProjects;

  const conversations = useConversationStore((state) => state.conversations);
  const workspace = useConversationStore((state) => state.workspace);
  const activeId = useConversationStore((state) => state.activeConversationId);
  const isLoading = useConversationStore((state) => state.isLoading);
  const streamingTitles = useConversationStore((state) => state.streamingTitles);
  const isActiveConversationAwaitingFirstReply = useChatStore((state) => {
    if (!activeId || !state.isStreaming || !state.currentStreamingId) return false;

    const activeMessages = state.messages.filter((message) => message.conversationId === activeId);
    if (activeMessages.length !== 2) return false;

    const hasUserMessage = activeMessages.some((message) => message.role === 'user');
    const hasStreamingAssistantMessage = activeMessages.some((message) => (
      message.id === state.currentStreamingId &&
      message.role === 'assistant' &&
      message.isStreaming === true
    ));

    return hasUserMessage && hasStreamingAssistantMessage;
  });


  const sidebarLogoSrc = resolvedTheme === 'light'
    ? '/logo/AREQA_logo_v4_black_word.png'
    : '/logo/AREQA_logo_v4_text.png';

  const { unreadCount, fetchMails } = useMailboxStore();
  const mailboxEnabled = useFeatureStore((state) => state.mailbox);

  useEffect(() => {
    if (!mailboxEnabled) {
      return;
    }
    fetchMails();
  }, [fetchMails, mailboxEnabled]);

  const pinnedIds = usePinnedConversationStore((state) => state.ids);
  useEffect(() => {
    usePinnedConversationStore.getState().hydrate();
  }, []);
  // Pinning a chat (here or on a project page) opens the Pinned group so it is seen.
  useEffect(() => usePinnedConversationStore.subscribe((state, previous) => {
    if (previous.hydrated && state.ids.length > previous.ids.length) setPinnedOpen(true);
  }), []);

  const handleNew = useCallback(async () => {
    // We don't create a conversation in DB yet (Lazy creation)
    // Just trigger the callback to reset the UI
    setOpenMenuId(null);
    onNew?.();
  }, [onNew]);

  const handleSelect = useCallback(
    async (id: string) => {
      if (openMenuId === id) return;
      logger.info('chat_history_sidebar_selected', {
        component: 'ConversationList',
        conversationId: id,
        activeConversationId: useConversationStore.getState().activeConversationId,
      });
      logConversationHistoryDebugEvent('chat_history_sidebar_selected', {
        component: 'ConversationList',
        conversationId: id,
        activeConversationId: useConversationStore.getState().activeConversationId,
      });
      await switchConversation(id);
      logger.info('chat_history_sidebar_selection_finished', {
        component: 'ConversationList',
        conversationId: id,
        activeConversationId: useConversationStore.getState().activeConversationId,
      });
      logConversationHistoryDebugEvent('chat_history_sidebar_selection_finished', {
        component: 'ConversationList',
        conversationId: id,
        activeConversationId: useConversationStore.getState().activeConversationId,
      });
      onSelect?.(id);
    },
    [onSelect, openMenuId]
  );

  const openProjectPage = useCallback((projectId: string | null) => {
    if (projectId) useProjectStore.getState().showProject(projectId);
    else useProjectStore.getState().showList();
    onSelectGumPanel?.('projects');
  }, [onSelectGumPanel]);

  const conversationMenu = useConversationMenu({
    closeMenu: () => setOpenMenuId(null),
    onDeleted: (id) => onDelete?.(id),
  });

  const isMobileViewport = useCallback(() => (
    window.matchMedia('(max-width: 768px)').matches
  ), []);

  const clearLongPressTimer = useCallback(() => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  const handleItemPointerDown = useCallback((id: string) => {
    if (!isMobileViewport()) return;

    longPressTriggeredRef.current = false;
    clearLongPressTimer();
    longPressTimerRef.current = window.setTimeout(() => {
      longPressTriggeredRef.current = true;
      setOpenMenuId(id);
    }, LONG_PRESS_MENU_MS);
  }, [clearLongPressTimer, isMobileViewport]);

  const handleItemPointerEnd = useCallback(() => {
    clearLongPressTimer();
  }, [clearLongPressTimer]);

  const handleItemClick = useCallback((id: string) => {
    if (longPressTriggeredRef.current) {
      longPressTriggeredRef.current = false;
      return;
    }

    void handleSelect(id);
  }, [handleSelect]);

  // The list and search show only the visible workspace (Chat or Topic Finder).
  const sortedConversations = useMemo(() => (
    conversations
      .filter((conversation) => conversationKindOf(conversation) === workspace)
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
  ), [conversations, workspace]);
  const pinnedIdSet = new Set(pinnedIds);
  const groups = [
    { key: 'pinned', label: t('pinned'), open: pinnedOpen, toggle: () => setPinnedOpen(!pinnedOpen),
      items: sortedConversations.filter((conversation) => pinnedIdSet.has(conversation.id)) },
    { key: 'recents', label: t('conversationRecents'), open: recentsOpen, toggle: () => setRecentsOpen((open) => !open),
      items: sortedConversations.filter((conversation) => !pinnedIdSet.has(conversation.id)) },
  ];
  const renderConversationRow = (conv: Conversation, nested = false) => {
    const isPinned = pinnedIds.includes(conv.id);
    const hasDefaultTitle = DEFAULT_CONVERSATION_TITLES.has(conv.title);
    const isGeneratingTitle = streamingTitles[conv.id] !== undefined;
    const isAwaitingInitialTitle = (
      conv.id === activeId &&
      hasDefaultTitle &&
      isActiveConversationAwaitingFirstReply
    );
    const isTitlePending = isGeneratingTitle || isAwaitingInitialTitle;
    const displayTitle = isGeneratingTitle
      ? streamingTitles[conv.id]
      : (hasDefaultTitle ? t('newChat') : conv.title || t('newChat'));
    const source = conversationBranchesEnabled && conv.branchOrigin
      ? conversations.find((item) => item.id === conv.branchOrigin?.conversationId)
      : undefined;
    const childBranches = conversationBranchesEnabled
      ? conversations.filter((item) => item.branchOrigin?.conversationId === conv.id)
      : [];
    // Nested rows sit under a pinned project; they share ids with Recents rows, so menus are keyed apart.
    const menuId = nested ? `nested:${conv.id}` : conv.id;
    const menuItems = conversationMenu.itemsFor(conv, [
      ...(source ? [{
        key: `branch:${source.id}`,
        label: menuLabel(<BranchIcon size={14} />, t('conversationBranchReturn')),
      }] : []),
      ...(childBranches.length ? [{
        key: 'branches',
        label: menuLabel(<BranchIcon size={14} />, t('conversationBranches')),
        children: childBranches.map((child) => ({ key: `branch:${child.id}`, label: child.title })),
      }] : []),
    ]);

    return (
      <Dropdown
        key={menuId}
        menu={{
          items: menuItems,
          onClick: ({ key, domEvent }) => {
            domEvent.stopPropagation();
            if (key === 'project-search') return; // Clicking the search field keeps the menu open.
            setOpenMenuId(null);
            if (key.startsWith('branch:')) {
              longPressTriggeredRef.current = false;
              void handleSelect(key.slice('branch:'.length));
            } else {
              conversationMenu.handleKey(conv, key, displayTitle);
            }
          },
        }}
        onOpenChange={(open) => {
          if (!open) conversationMenu.resetProjectQuery();
          setOpenMenuId((current) => (open ? menuId : current === menuId ? null : current));
        }}
        open={openMenuId === menuId}
        placement="bottomRight"
        trigger={['contextMenu']}
      >
        <div
          data-conversation-id={nested ? undefined : conv.id}
          data-project-conversation-id={nested ? conv.id : undefined}
          className={[
            'areqa-conversation-item',
            nested && 'areqa-conversation-project-child',
            conv.id === activeId && 'areqa-conversation-item-active',
          ].filter(Boolean).join(' ')}
          onClick={() => handleItemClick(conv.id)}
          onPointerCancel={handleItemPointerEnd}
          onPointerDown={() => handleItemPointerDown(menuId)}
          onPointerLeave={handleItemPointerEnd}
          onPointerUp={handleItemPointerEnd}
        >
          {!nested && isPinned && <span className="areqa-conversation-item-icon"><MessageCircle size={17} aria-hidden="true" /></span>}
          {!nested && !isPinned && conversationBranchesEnabled && conv.branchOrigin && <span className="areqa-conversation-item-icon">
            <BranchIcon />
          </span>}
          <div className="areqa-conversation-item-content">
            <span
              className="areqa-conversation-item-title conv-title"
              title={isTitlePending ? undefined : displayTitle}
            >
              {isTitlePending ? (
                <span
                  className="areqa-conversation-title-skeleton"
                  aria-label={t('newChat')}
                  role="status"
                />
              ) : (
                <span>{displayTitle}</span>
              )}
            </span>
          </div>
          <button
            className="areqa-conversation-menu-btn conversation-menu-btn"
            onClick={(event) => {
              event.stopPropagation();
              setOpenMenuId((current) => current === menuId ? null : menuId);
            }}
            aria-haspopup="menu"
            aria-expanded={openMenuId === menuId}
            onKeyDown={(event) => {
              if (event.key === 'Escape') setOpenMenuId(null);
            }}
            title={t('conversationMenu')}
            type="button"
          >
            <MoreHorizontal size={16} />
          </button>
        </div>
      </Dropdown>
    );
  };

  /** A pinned project with its newest chats nested under it (image 02). */
  const renderPinnedProject = (project: Project) => {
    const projectConversations = conversations
      .filter((conversation) => conversation.projectId === project.id)
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
    const isActive = project.id === activeProjectId;
    return (
      <div key={`project:${project.id}`} className="areqa-conversation-project">
        <Dropdown
          open={projectMenuId === project.id}
          onOpenChange={(open) => setProjectMenuId(open ? project.id : null)}
          trigger={['contextMenu']}
          placement="bottomRight"
          menu={{
            items: [
              { key: 'pin', label: menuLabel(<PinOff size={14} />, t('projectUnpin')) },
              { key: 'rename', label: menuLabel(<Pencil size={14} />, t('projectEditDetails')) },
              { type: 'divider' },
              { key: 'delete', danger: true, label: menuLabel(<Trash2 size={14} />, t('delete')) },
            ],
            onClick: ({ key, domEvent }) => {
              domEvent.stopPropagation();
              setProjectMenuId(null);
              if (key === 'pin') void useProjectStore.getState().update(project.id, { isPinned: false });
              else if (key === 'rename') setRenameProjectId(project.id);
              else if (key === 'delete') {
                modal.confirm({
                  title: t('projectDeleteConfirm', { name: project.name }),
                  okText: t('delete'),
                  okButtonProps: { danger: true },
                  onOk: () => useProjectStore.getState().remove(project.id),
                });
              }
            },
          }}
        >
          <div
            data-project-id={project.id}
            className={['areqa-conversation-item', 'areqa-conversation-project-item',
              isActive && 'areqa-conversation-item-active'].filter(Boolean).join(' ')}
            onClick={() => openProjectPage(project.id)}
          >
            <span className="areqa-conversation-item-icon"><ProjectIcon size={17} /></span>
            <div className="areqa-conversation-item-content">
              <span className="areqa-conversation-item-title" title={project.name}><span>{project.name}</span></span>
            </div>
            <button
              className="areqa-conversation-menu-btn conversation-menu-btn"
              onClick={(event) => {
                event.stopPropagation();
                setProjectMenuId((current) => current === project.id ? null : project.id);
              }}
              aria-haspopup="menu"
              aria-expanded={projectMenuId === project.id}
              title={t('projectMenu')}
              type="button"
            >
              <MoreHorizontal size={16} />
            </button>
          </div>
        </Dropdown>
        {projectConversations.length > 0 && (
          // Nested chats hang off a thin guide line under the project icon (sidebar reference).
          <div className="areqa-conversation-project-children">
            {projectConversations.slice(0, PINNED_PROJECT_PREVIEW_COUNT).map((conv) => renderConversationRow(conv, true))}
            {projectConversations.length > PINNED_PROJECT_PREVIEW_COUNT && (
              <button type="button" className="areqa-conversation-item areqa-conversation-project-child areqa-conversation-project-more"
                onClick={() => openProjectPage(project.id)}>
                {t('projectViewAll')}
              </button>
            )}
          </div>
        )}
      </div>
    );
  };

  const normalizedQuery = searchQuery.trim().toLocaleLowerCase();
  const searchResults = searchOpen ? sortedConversations.filter((conversation) => (
    [conversation.title, conversation.lastMessagePreview].some((value) =>
      value?.toLocaleLowerCase().includes(normalizedQuery))
  )) : [];

  const closeSearch = () => {
    setSearchOpen(false);
    setSearchQuery('');
  };

  return (
    <div className={['areqa-conversation-list', className].filter(Boolean).join(' ')}>
      {/* Logo & Toggle Area */}
      <div className={externalSidebarToggle
        ? 'areqa-conversation-logo-row areqa-conversation-logo-row-external-toggle'
        : 'areqa-conversation-logo-row'}>
        <button
          type="button"
          className="areqa-conversation-logo-wrapper"
          onClick={handleNew}
          aria-label={t('conversationHome')}
          title={t('conversationHome')}
        >
          <Image
            src={sidebarLogoSrc}
            alt="AREQA Logo" 
            width={100}
            height={36}
            unoptimized
            className="areqa-conversation-logo"
            draggable={false}
            priority
          />
        </button>
        <div className="areqa-conversation-logo-actions">
          <WorkspaceSwitch variant="icons" onLeaveConversation={handleNew} />
          {!externalSidebarToggle && (
            <button
              className="areqa-conversation-toggle-button"
              onClick={onToggleSidebar}
              title={t('closeSidebar')}
            >
              <PanelLeftClose size={20} />
            </button>
          )}
        </div>
      </div>

      {/* Action Area */}
      <div className="areqa-conversation-actions">
        <button type="button" className="areqa-conversation-new-button" onClick={handleNew}>
          <Plus size={18} />
          <span>{t('newChat')}</span>
        </button>
        <button type="button" className="areqa-conversation-search-button" onClick={() => setSearchOpen(true)}>
          <Search size={17} aria-hidden="true" />
          <span>{t('conversationSearch')}</span>
        </button>
        {isSignedIn && (
          <div className="areqa-conversation-projects-nav" data-active={projectsActive}>
            <button type="button" className="areqa-conversation-search-button" aria-current={projectsActive ? 'page' : undefined}
              onClick={() => openProjectPage(null)}>
              <ProjectIcon size={17} />
              <span>{t('projects')}</span>
            </button>
            <Tooltip title={t('projectCreate')} placement="right">
              <button
                type="button"
                className="areqa-conversation-projects-create"
                aria-label={t('projectCreate')}
                onClick={() => setCreateProjectOpen(true)}
              >
                <Plus size={15} aria-hidden="true" />
              </button>
            </Tooltip>
          </div>
        )}
        {mailboxEnabled && (
          <button className="areqa-conversation-panel-button" onClick={() => onSelectGumPanel?.('mailbox')}>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <MailIcon size={18} />
              {unreadCount > 0 && (
                <span style={{
                  position: 'absolute', top: -4, right: -4,
                  backgroundColor: 'red', color: 'white',
                  borderRadius: '50%', width: 14, height: 14,
                  fontSize: 10, display: 'flex',
                  justifyContent: 'center', alignItems: 'center'
                }}>
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </div>
            <span>{t('mailbox')}</span>
          </button>
        )}
      </div>

      {/* List Area */}
      <div className="areqa-conversation-scroll-list">
        {isLoading && conversations.length === 0 ? (
          <div className="areqa-conversation-loading">
            <Spin size="small" />
          </div>
        ) : groups.map(({ key, label, items, open, toggle }) => {
          const projectsInGroup = key === 'pinned' && hasPinnedProjects ? pinnedProjects : [];
          return (
            <section key={key} className="areqa-conversation-group">
              <button type="button" className="areqa-conversation-group-title" aria-expanded={open} onClick={toggle}>
                {label}
                <ChevronRight size={13} aria-hidden="true" />
              </button>
              {open && items.length === 0 && projectsInGroup.length === 0 && (
                <p className="areqa-conversation-empty-text">{t(key === 'pinned' ? 'noPinnedConversations' : 'noConversations')}</p>
              )}
              {open && projectsInGroup.map((project) => renderPinnedProject(project))}
              {open && items.map((conv) => renderConversationRow(conv))}
            </section>
          );
        })}
      </div>

      {/* User Auth UI Area */}
      <div className="areqa-conversation-account-footer">
        <UserAuthUI
          onOpenMemory={() => onSelectGumPanel?.('memory')}
          onOpenNotes={() => onSelectGumPanel?.('notes')}
        />
      </div>
      <Modal
        open={searchOpen}
        onCancel={closeSearch}
        title={t('conversationSearch')}
        footer={null}
        destroyOnHidden
      >
        <Input
          autoFocus
          allowClear
          prefix={<Search size={16} aria-hidden="true" />}
          aria-label={t('conversationSearch')}
          placeholder={t('conversationSearchPlaceholder')}
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
        <div className="areqa-conversation-search-results">
          {searchResults.length === 0 && (
            <p role="status" className="areqa-conversation-empty-text">{t('conversationSearchEmpty')}</p>
          )}
          {searchResults.map((conversation) => (
            <button type="button" key={conversation.id} className="areqa-conversation-search-result" onClick={() => {
              closeSearch();
              void handleSelect(conversation.id);
            }}>
              {DEFAULT_CONVERSATION_TITLES.has(conversation.title) ? t('newChat') : conversation.title || t('newChat')}
            </button>
          ))}
        </div>
      </Modal>
      {conversationMenu.dialogs}
      <ProjectFormModal
        open={createProjectOpen}
        onClose={() => setCreateProjectOpen(false)}
        onSubmit={async ({ name, description }) => {
          const project = await useProjectStore.getState().create(name, description);
          openProjectPage(project.id);
        }}
      />
      <ProjectFormModal
        open={renameProjectId !== null}
        mode="edit"
        initialValues={(() => {
          const project = projects.find((item) => item.id === renameProjectId);
          return { name: project?.name ?? '', description: project?.description ?? '' };
        })()}
        onClose={() => setRenameProjectId(null)}
        onSubmit={async (values) => {
          if (renameProjectId) await useProjectStore.getState().update(renameProjectId, values);
        }}
      />
    </div>
  );
}
