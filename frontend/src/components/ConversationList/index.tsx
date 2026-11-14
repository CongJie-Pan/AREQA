'use client';

/**
 * ConversationList Component
 * Sidebar displaying conversation history grouped by time
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { App, Dropdown, Input, Modal, Spin } from 'antd';
import type { MenuProps } from 'antd';
import { MoreHorizontal, Pencil, Pin, PinOff, Plus, Search, ChevronRight, Trash2, PanelLeftClose, Mail as MailIcon } from 'lucide-react';
import { BranchIcon, conversationBranchesEnabled } from '@/components/ConversationBranch/BranchIcon';
import { useConversationStore } from '@/store/conversation';
import { useChatStore } from '@/store/chat';
import { useMailboxStore } from '@/store/mailbox';
import { useFeatureStore } from '@/store/features';
import { useStyles } from './styles';
import { SidePanelType } from '@/types/panel';
import {
  logConversationHistoryDebugEvent,
  switchConversation,
  deleteConversation as deleteConversationService,
} from '@/services/chat';
import { databaseService } from '@/services/database';
import { UserAuthUI } from '../Auth';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { logger } from '@/utils/logger';

const PINNED_CONVERSATION_IDS_KEY = 'areqa:pinned-conversation-ids';
const LONG_PRESS_MENU_MS = 520;
const DEFAULT_CONVERSATION_TITLES = new Set(['新對話', '新对话']);

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
}: ConversationListProps) {
  const { styles, cx } = useStyles();
  const { message: antMessageApi } = App.useApp();
  const { resolvedTheme, t } = useUserPreferences();
  const longPressTimerRef = useRef<number | null>(null);
  const longPressTriggeredRef = useRef(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [pinnedOpen, setPinnedOpen] = useState(false);
  const [recentsOpen, setRecentsOpen] = useState(true);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [pinnedIds, setPinnedIds] = useState<string[]>([]);
  const [renameTargetId, setRenameTargetId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const [marqueeTitleWidths, setMarqueeTitleWidths] = useState<Record<string, number>>({});
  const titleRefs = useRef<Record<string, HTMLSpanElement | null>>({});

  const conversations = useConversationStore((state) => state.conversations);
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

  useEffect(() => {
    try {
      const storedValue = window.localStorage.getItem(PINNED_CONVERSATION_IDS_KEY);
      const parsedValue = storedValue ? JSON.parse(storedValue) : [];
      if (Array.isArray(parsedValue)) {
        setPinnedIds(parsedValue.filter((id): id is string => typeof id === 'string'));
      }
    } catch {
      setPinnedIds([]);
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(PINNED_CONVERSATION_IDS_KEY, JSON.stringify(pinnedIds));
    } catch {
      // Pinning is a local UI preference. Storage failures should not block chat usage.
    }
  }, [pinnedIds]);

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

  const handleDelete = useCallback(
    async (id: string) => {
      await deleteConversationService(id);
      setPinnedIds((current) => current.filter((pinnedId) => pinnedId !== id));
      onDelete?.(id);
    },
    [onDelete]
  );

  const openRenameDialog = useCallback((id: string, title: string) => {
    setRenameTargetId(id);
    setRenameValue(title);
  }, []);

  const closeRenameDialog = useCallback(() => {
    if (isRenaming) return;
    setRenameTargetId(null);
    setRenameValue('');
  }, [isRenaming]);

  const submitRename = useCallback(async () => {
    if (!renameTargetId) return;
    const nextTitle = renameValue.trim();
    if (!nextTitle) {
      antMessageApi.warning(t('enterConversationName'));
      return;
    }

    setIsRenaming(true);
    try {
      await databaseService.conversation.update(renameTargetId, { title: nextTitle });
      useConversationStore.getState().updateConversation(renameTargetId, {
        title: nextTitle,
        updatedAt: new Date(),
      });
      antMessageApi.success(t('renameSuccess'));
      setRenameTargetId(null);
      setRenameValue('');
    } catch {
      antMessageApi.error(t('renameFailed'));
    } finally {
      setIsRenaming(false);
    }
  }, [antMessageApi, renameTargetId, renameValue, t]);

  const togglePinned = useCallback((id: string) => {
    if (!pinnedIds.includes(id)) setPinnedOpen(true);
    setPinnedIds((current) => (
      current.includes(id)
        ? current.filter((pinnedId) => pinnedId !== id)
        : [id, ...current]
    ));
  }, [pinnedIds]);

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

  const handleTitlePointerEnter = useCallback((id: string) => {
    const titleNode = titleRefs.current[id];
    if (!titleNode) return;

    const isOverflowing = titleNode.scrollWidth > titleNode.clientWidth;
    const marqueeWidth = isOverflowing ? titleNode.clientWidth : 0;
    setMarqueeTitleWidths((current) => (
      current[id] === marqueeWidth ? current : { ...current, [id]: marqueeWidth }
    ));
  }, []);

  const sortedConversations = useMemo(() => (
    [...conversations].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
  ), [conversations]);
  const pinnedIdSet = new Set(pinnedIds);
  const groups = [
    { key: 'pinned', label: t('pinned'), open: pinnedOpen, toggle: () => setPinnedOpen((open) => !open),
      items: sortedConversations.filter((conversation) => pinnedIdSet.has(conversation.id)) },
    { key: 'recents', label: t('conversationRecents'), open: recentsOpen, toggle: () => setRecentsOpen((open) => !open),
      items: sortedConversations.filter((conversation) => !pinnedIdSet.has(conversation.id)) },
  ];
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
    <div className={cx('areqa-conversation-list', styles.container, className)}>
      {/* Logo & Toggle Area */}
      <div className={cx(
        'areqa-conversation-logo-row',
        styles.logoContainer,
        externalSidebarToggle && 'areqa-conversation-logo-row-external-toggle',
        externalSidebarToggle && styles.logoContainerExternalToggle,
      )}>
        <button
          type="button"
          className={cx('areqa-conversation-logo-wrapper', styles.logoWrapper)}
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
            className={cx('areqa-conversation-logo', styles.logo)}
            draggable={false}
            priority
          />
        </button>
        {!externalSidebarToggle && (
          <button
            className={cx('areqa-conversation-toggle-button', styles.toggleButton)}
            onClick={onToggleSidebar}
            title={t('closeSidebar')}
          >
            <PanelLeftClose size={20} />
          </button>
        )}
      </div>

      {/* Action Area */}
      <div className={cx('areqa-conversation-actions', styles.header)}>
        <button type="button" className={cx('areqa-conversation-new-button', styles.newButton)} onClick={handleNew}>
          <Plus size={18} />
          <span>{t('newChat')}</span>
        </button>
        <button type="button" className={styles.searchButton} onClick={() => setSearchOpen(true)}>
          <Search size={17} aria-hidden="true" />
          <span>{t('conversationSearch')}</span>
        </button>
        {mailboxEnabled && (
          <button className={cx('areqa-conversation-panel-button', styles.gumButton)} onClick={() => onSelectGumPanel?.('mailbox')}>
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
      <div className={cx('areqa-conversation-scroll-list', styles.list)}>
        {isLoading && conversations.length === 0 ? (
          <div className={cx('areqa-conversation-loading', styles.loading)}>
            <Spin size="small" />
          </div>
        ) : groups.map(({ key, label, items, open, toggle }) => (
          <section key={key} className={styles.group}>
            <button type="button" className={styles.groupTitle} aria-expanded={open} onClick={toggle}>
              {label}
              <ChevronRight size={13} aria-hidden="true" />
            </button>
            {open && items.length === 0 && (
              <p className={styles.emptyText}>{t(key === 'pinned' ? 'noPinnedConversations' : 'noConversations')}</p>
            )}
            {open && items.map((conv) => {
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
              const menuLabel = (icon: React.ReactNode, label: string) => (
                <span className={styles.menuLabel}>{icon}<span>{label}</span></span>
              );
              const menuItems: MenuProps['items'] = [
                { key: 'rename', label: menuLabel(<Pencil size={14} />, t('rename')) },
                { key: 'pin', label: menuLabel(
                  isPinned ? <PinOff size={14} /> : <Pin size={14} />, t(isPinned ? 'unpin' : 'pin'),
                ) },
                ...(source ? [{
                  key: `branch:${source.id}`,
                  label: menuLabel(<BranchIcon size={14} />, t('conversationBranchReturn')),
                }] : []),
                ...(childBranches.length ? [{
                  key: 'branches',
                  label: menuLabel(<BranchIcon size={14} />, t('conversationBranches')),
                  children: childBranches.map((child) => ({ key: `branch:${child.id}`, label: child.title })),
                }] : []),
                { type: 'divider' },
                { key: 'delete', danger: true, label: menuLabel(<Trash2 size={14} />, t('delete')) },
              ];

              return (
                <Dropdown
                  key={conv.id}
                  menu={{
                    items: menuItems,
                    onClick: ({ key, domEvent }) => {
                      domEvent.stopPropagation();
                      setOpenMenuId(null);
                      if (key.startsWith('branch:')) {
                        longPressTriggeredRef.current = false;
                        void handleSelect(key.slice('branch:'.length));
                      } else if (key === 'rename') {
                        openRenameDialog(conv.id, displayTitle);
                      } else if (key === 'pin') {
                        togglePinned(conv.id);
                      } else if (key === 'delete') {
                        void handleDelete(conv.id);
                      }
                    },
                  }}
                  onOpenChange={(open) => setOpenMenuId(open ? conv.id : null)}
                  open={openMenuId === conv.id}
                  placement="bottomRight"
                  trigger={['contextMenu']}
                >
                  <div
                    className={cx(
                      'areqa-conversation-item',
                      styles.item,
                      conv.id === activeId && styles.itemActive
                    )}
                    onClick={() => handleItemClick(conv.id)}
                    onPointerCancel={handleItemPointerEnd}
                    onPointerDown={() => handleItemPointerDown(conv.id)}
                    onPointerEnter={() => handleTitlePointerEnter(conv.id)}
                    onPointerLeave={handleItemPointerEnd}
                    onPointerUp={handleItemPointerEnd}
                  >
                    {conversationBranchesEnabled && conv.branchOrigin && <span className={styles.itemIcon}>
                      <BranchIcon />
                    </span>}
                    <div className={cx('areqa-conversation-item-content', styles.itemContent)}>
                      <span
                        className={cx('areqa-conversation-item-title', styles.itemTitle, 'conv-title')}
                        data-overflow={marqueeTitleWidths[conv.id] ? 'true' : undefined}
                        onPointerEnter={() => handleTitlePointerEnter(conv.id)}
                        ref={(node) => {
                          titleRefs.current[conv.id] = node;
                        }}
                        style={{
                          '--areqa-title-marquee-width': `${marqueeTitleWidths[conv.id] || 0}px`,
                        } as React.CSSProperties}
                      >
                        {isTitlePending ? (
                          <span
                            className={styles.titleSkeleton}
                            aria-label={t('newChat')}
                            role="status"
                          />
                        ) : (
                          <span>{displayTitle}</span>
                        )}
                      </span>
                    </div>
                    {isPinned && <Pin size={13} className={styles.pinnedIcon} />}
                    <button
                      className={cx(styles.menuBtn, 'conversation-menu-btn')}
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpenMenuId(conv.id);
                      }}
                      title={t('conversationMenu')}
                      type="button"
                    >
                      <MoreHorizontal size={16} />
                    </button>
                  </div>
                </Dropdown>
              );
            })}
          </section>
        ))}
      </div>

      {/* User Auth UI Area */}
      <div className={styles.accountFooter}>
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
        <div className={styles.searchResults}>
          {searchResults.length === 0 && (
            <p role="status" className={styles.emptyText}>{t('conversationSearchEmpty')}</p>
          )}
          {searchResults.map((conversation) => (
            <button type="button" key={conversation.id} className={styles.searchResult} onClick={() => {
              closeSearch();
              void handleSelect(conversation.id);
            }}>
              {DEFAULT_CONVERSATION_TITLES.has(conversation.title) ? t('newChat') : conversation.title || t('newChat')}
            </button>
          ))}
        </div>
      </Modal>
      <Modal
        confirmLoading={isRenaming}
        okButtonProps={{ disabled: !renameValue.trim() }}
        okText={t('save')}
        onCancel={closeRenameDialog}
        onOk={submitRename}
        open={renameTargetId !== null}
        title={t('renameTitle')}
      >
        <Input
          autoFocus
          maxLength={80}
          onChange={(event) => setRenameValue(event.target.value)}
          onPressEnter={submitRename}
          placeholder={t('renamePlaceholder')}
          value={renameValue}
        />
      </Modal>
    </div>
  );
}
