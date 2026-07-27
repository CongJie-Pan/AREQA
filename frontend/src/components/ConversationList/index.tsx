'use client';

/**
 * ConversationList Component
 * Sidebar displaying conversation history grouped by time
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { App, Dropdown, Input, Modal, Spin } from 'antd';
import type { MenuProps } from 'antd';
import { MoreHorizontal, Pencil, Pin, PinOff, Plus, MessageSquare, Trash2, MessagesSquare, PanelLeftClose, BrainCircuit, Mail as MailIcon } from 'lucide-react';
import { useConversationStore } from '@/store/conversation';
import { useMailboxStore } from '@/store/mailbox';
import { useStyles } from './styles';
import { SidePanelType } from '@/types/panel';
import { switchConversation, deleteConversation as deleteConversationService } from '@/services/chat';
import { databaseService } from '@/services/database';
import { UserAuthUI } from '../Auth';

const PINNED_CONVERSATION_IDS_KEY = 'areqa:pinned-conversation-ids';
const LONG_PRESS_MENU_MS = 520;

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
  


  const { unreadCount, fetchMails } = useMailboxStore();

  useEffect(() => {
    fetchMails();
  }, [fetchMails]);

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
      antMessageApi.warning('請輸入對話名稱');
      return;
    }

    setIsRenaming(true);
    try {
      await databaseService.conversation.update(renameTargetId, { title: nextTitle });
      useConversationStore.getState().updateConversation(renameTargetId, {
        title: nextTitle,
        updatedAt: new Date(),
      });
      antMessageApi.success('已重新命名對話');
      setRenameTargetId(null);
      setRenameValue('');
    } catch {
      antMessageApi.error('重新命名失敗，請稍後再試');
    } finally {
      setIsRenaming(false);
    }
  }, [antMessageApi, renameTargetId, renameValue]);

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
      今天: [],
      昨天: [],
      過去七天: [],
      更早以前: [],
    };

    const now = new Date();
    now.setHours(0, 0, 0, 0);

    unpinnedConversations.forEach((conv) => {
      const date = new Date(conv.updatedAt);
      date.setHours(0, 0, 0, 0);
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

      if (diffDays === 0) groups['今天'].push(conv);
      else if (diffDays === 1) groups['昨天'].push(conv);
      else if (diffDays < 7) groups['過去七天'].push(conv);
      else groups['更早以前'].push(conv);
    });

    return [
      ...(pinnedConversations.length > 0 ? [['釘選', pinnedConversations] as const] : []),
      ...Object.entries(groups).filter(([, items]) => items.length > 0),
    ];
  }, [conversations, pinnedIds]);

  return (
    <div className={cx(styles.container, className)}>
      {/* Logo & Toggle Area */}
      <div className={styles.logoContainer}>
        <div className={styles.logoWrapper}>
          <Image 
            src="/logo/areqa_icon_v3.png" 
            alt="AREQA Logo" 
            width={40} 
            height={40}
            className={styles.logo}
            priority
          />
        </div>
        <button 
          className={styles.toggleButton} 
          onClick={onToggleSidebar}
          title="關閉側邊欄"
        >
          <PanelLeftClose size={20} />
        </button>
      </div>

      {/* Action Area */}
      <div className={styles.header}>
        <button className={styles.newButton} onClick={handleNew}>
          <Plus size={18} />
          <span>新對話</span>
        </button>
        <div className={styles.divider} />
        <button className={styles.gumButton} onClick={() => onSelectGumPanel?.('memory')}>
          <BrainCircuit size={18} />
          <span>瀏覽記憶</span>
        </button>
        <button className={styles.gumButton} onClick={() => onSelectGumPanel?.('mailbox')}>
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
          <span>信箱</span>
        </button>
      </div>

      {/* List Area */}
      <div className={styles.list}>
        {isLoading ? (
          <div className={styles.loading}>
            <Spin size="small" />
          </div>
        ) : conversations.length === 0 ? (
          <div className={styles.empty}>
            <MessagesSquare size={32} className={styles.emptyIcon} />
            <p className={styles.emptyText}>尚無對話紀錄</p>
          </div>
        ) : (
          groupedConversations.map(([group, items]) => (
            <React.Fragment key={group}>
              <div className={styles.groupTitle}>{group}</div>
              {items.map((conv) => {
                const isPinned = pinnedIds.includes(conv.id);
                const displayTitle = streamingTitles[conv.id] !== undefined
                  ? streamingTitles[conv.id]
                  : conv.title || '新對話';
                const menuItems: MenuProps['items'] = [
                  {
                    key: 'rename',
                    icon: <Pencil size={14} />,
                    label: '重新命名',
                  },
                  {
                    key: 'pin',
                    icon: isPinned ? <PinOff size={14} /> : <Pin size={14} />,
                    label: isPinned ? '取消釘選' : '釘選聊天',
                  },
                  {
                    key: 'delete',
                    danger: true,
                    icon: <Trash2 size={14} />,
                    label: '刪除',
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
                        styles.item,
                        conv.id === activeId && styles.itemActive
                      )}
                      onClick={() => handleItemClick(conv.id)}
                      onPointerCancel={handleItemPointerEnd}
                      onPointerDown={() => handleItemPointerDown(conv.id)}
                      onPointerLeave={handleItemPointerEnd}
                      onPointerUp={handleItemPointerEnd}
                    >
                      <MessageSquare size={16} className={styles.itemIcon} />
                      <div className={styles.itemContent}>
                        <span className={cx(styles.itemTitle, 'conv-title')}>
                          {streamingTitles[conv.id] !== undefined ? (
                            <>
                              {displayTitle}
                              <span className={styles.cursor} />
                            </>
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
                        title="對話選單"
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
      <UserAuthUI />
      <Modal
        confirmLoading={isRenaming}
        okButtonProps={{ disabled: !renameValue.trim() }}
        okText="儲存"
        onCancel={closeRenameDialog}
        onOk={submitRename}
        open={renameTargetId !== null}
        title="重新命名對話"
      >
        <Input
          autoFocus
          maxLength={80}
          onChange={(event) => setRenameValue(event.target.value)}
          onPressEnter={submitRename}
          placeholder="輸入新的對話名稱"
          value={renameValue}
        />
      </Modal>
    </div>
  );
}
