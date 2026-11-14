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
        ) : groups.map(({ key, label, items, open, toggle }) => (
          <section key={key} className="areqa-conversation-group">
            <button type="button" className="areqa-conversation-group-title" aria-expanded={open} onClick={toggle}>
              {label}
              <ChevronRight size={13} aria-hidden="true" />
            </button>
            {open && items.length === 0 && (
              <p className="areqa-conversation-empty-text">{t(key === 'pinned' ? 'noPinnedConversations' : 'noConversations')}</p>
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
                <span className="areqa-conversation-menu-label">{icon}<span>{label}</span></span>
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
                  onOpenChange={(open) => setOpenMenuId((current) => (
                    open ? conv.id : current === conv.id ? null : current
                  ))}
                  open={openMenuId === conv.id}
                  placement="bottomRight"
                  trigger={['contextMenu']}
                >
                  <div
                    className={conv.id === activeId
                      ? 'areqa-conversation-item areqa-conversation-item-active'
                      : 'areqa-conversation-item'}
                    onClick={() => handleItemClick(conv.id)}
                    onPointerCancel={handleItemPointerEnd}
                    onPointerDown={() => handleItemPointerDown(conv.id)}
                    onPointerLeave={handleItemPointerEnd}
                    onPointerUp={handleItemPointerEnd}
                  >
                    {conversationBranchesEnabled && conv.branchOrigin && <span className="areqa-conversation-item-icon">
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
                    {isPinned && <Pin size={13} className="areqa-conversation-pinned-icon" />}
                    <button
                      className="areqa-conversation-menu-btn conversation-menu-btn"
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpenMenuId((current) => current === conv.id ? null : conv.id);
                      }}
                      aria-haspopup="menu"
                      aria-expanded={openMenuId === conv.id}
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
            })}
          </section>
        ))}
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
