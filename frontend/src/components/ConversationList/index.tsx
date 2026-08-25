'use client';

/**
 * ConversationList Component
 * Sidebar displaying conversation history grouped by time
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { App, Dropdown, Input, Modal, Spin } from 'antd';
import type { MenuProps } from 'antd';
import { MoreHorizontal, Pencil, Pin, PinOff, Plus, MessageSquare, Trash2, MessagesSquare, PanelLeftClose, Mail as MailIcon } from 'lucide-react';
import { useConversationStore } from '@/store/conversation';
import { useChatStore } from '@/store/chat';
import { useMailboxStore } from '@/store/mailbox';
import { useFeatureStore } from '@/store/features';
import { useStyles } from './styles';
import { SidePanelType } from '@/types/panel';
import { switchConversation, deleteConversation as deleteConversationService } from '@/services/chat';
import { databaseService } from '@/services/database';
import { UserAuthUI } from '../Auth';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';

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
  onSelectGumPanel,
  className,
}: ConversationListProps) {
  const { styles, cx } = useStyles();
  const { message: antMessageApi } = App.useApp();
  const { resolvedTheme, t } = useUserPreferences();
  const longPressTimerRef = useRef<number | null>(null);
  const longPressTriggeredRef = useRef(false);
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
    onNew?.();
  }, [onNew]);

  const handleSelect = useCallback(
    async (id: string) => {
      if (openMenuId === id) return;
      await switchConversation(id);
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
    setPinnedIds((current) => (
      current.includes(id)
        ? current.filter((pinnedId) => pinnedId !== id)
        : [id, ...current]
    ));
  }, []);

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

  /**
   * Group conversations by date
   */
  const groupedConversations = useMemo(() => {
    const pinnedIdSet = new Set(pinnedIds);
    const pinnedConversations = conversations.filter((conv) => pinnedIdSet.has(conv.id));
    const unpinnedConversations = conversations.filter((conv) => !pinnedIdSet.has(conv.id));
    const groups: { [key: string]: typeof conversations } = {
      [t('today')]: [],
      [t('yesterday')]: [],
      [t('previousSevenDays')]: [],
      [t('older')]: [],
    };

    const now = new Date();
    now.setHours(0, 0, 0, 0);

    unpinnedConversations.forEach((conv) => {
      const date = new Date(conv.updatedAt);
      date.setHours(0, 0, 0, 0);
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

      if (diffDays === 0) groups[t('today')].push(conv);
      else if (diffDays === 1) groups[t('yesterday')].push(conv);
      else if (diffDays < 7) groups[t('previousSevenDays')].push(conv);
      else groups[t('older')].push(conv);
    });

    return [
      ...(pinnedConversations.length > 0 ? [[t('pinned'), pinnedConversations] as const] : []),
      ...Object.entries(groups).filter(([, items]) => items.length > 0),
    ];
  }, [conversations, pinnedIds, t]);

  return (
    <div className={cx('areqa-conversation-list', styles.container, className)}>
      {/* Logo & Toggle Area */}
      <div className={cx('areqa-conversation-logo-row', styles.logoContainer)}>
        <div className={cx('areqa-conversation-logo-wrapper', styles.logoWrapper)}>
          <Image 
            src={sidebarLogoSrc} 
            alt="AREQA Logo" 
            width={164} 
            height={40}
            className={cx('areqa-conversation-logo', styles.logo)}
            draggable={false}
            priority
          />
        </div>
        <button 
          className={cx('areqa-conversation-toggle-button', styles.toggleButton)} 
          onClick={onToggleSidebar}
          title={t('closeSidebar')}
        >
          <PanelLeftClose size={20} />
        </button>
      </div>

      {/* Action Area */}
      <div className={cx('areqa-conversation-actions', styles.header)}>
        <button className={cx('areqa-conversation-new-button', styles.newButton)} onClick={handleNew}>
          <Plus size={18} />
          <span>{t('newChat')}</span>
        </button>
        <div className={cx('areqa-conversation-divider', styles.divider)} />
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
        {isLoading ? (
          <div className={cx('areqa-conversation-loading', styles.loading)}>
            <Spin size="small" />
          </div>
        ) : conversations.length === 0 ? (
          <div className={cx('areqa-conversation-empty', styles.empty)}>
            <MessagesSquare size={32} className={cx('areqa-conversation-empty-icon', styles.emptyIcon)} />
            <p className={cx('areqa-conversation-empty-text', styles.emptyText)}>{t('noConversations')}</p>
          </div>
        ) : (
          groupedConversations.map(([group, items]) => (
            <React.Fragment key={group}>
              <div className={cx('areqa-conversation-group-title', styles.groupTitle)}>{group}</div>
              {items.map((conv) => {
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
                const menuItems: MenuProps['items'] = [
                  {
                    key: 'rename',
                    icon: <Pencil size={14} />,
                    label: t('rename'),
                  },
                  {
                    key: 'pin',
                    icon: isPinned ? <PinOff size={14} /> : <Pin size={14} />,
                    label: isPinned ? t('unpin') : t('pin'),
                  },
                  {
                    key: 'delete',
                    danger: true,
                    icon: <Trash2 size={14} />,
                    label: t('delete'),
                  },
                ];

                return (
                  <Dropdown
                    key={conv.id}
                    menu={{
                      items: menuItems,
                      onClick: ({ key, domEvent }) => {
                        domEvent.stopPropagation();
                        setOpenMenuId(null);
                        if (key === 'rename') {
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
                      onPointerLeave={handleItemPointerEnd}
                      onPointerUp={handleItemPointerEnd}
                    >
                      <MessageSquare size={16} className={cx('areqa-conversation-item-icon', styles.itemIcon)} />
                      <div className={cx('areqa-conversation-item-content', styles.itemContent)}>
                        <span className={cx('areqa-conversation-item-title', styles.itemTitle, 'conv-title')}>
                          {isTitlePending ? (
                            <span
                              className={styles.titleSkeleton}
                              aria-label={t('newChat')}
                              role="status"
                            />
                          ) : (
                            displayTitle
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
            </React.Fragment>
          ))
        )}
      </div>

      {/* User Auth UI Area */}
      <UserAuthUI onOpenMemory={() => onSelectGumPanel?.('memory')} />
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
