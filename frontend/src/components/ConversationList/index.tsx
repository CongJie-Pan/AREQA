'use client';

/**
 * ConversationList Component
 * Sidebar displaying conversation history grouped by time
 */

import React, { useCallback, useMemo } from 'react';
import Image from 'next/image';
import { Spin } from 'antd';
import { Plus, MessageSquare, Trash2, MessagesSquare, PanelLeftClose } from 'lucide-react';
import { useConversationStore } from '@/store/conversation';
import { switchConversation, deleteConversation as deleteConversationService } from '@/services/chat';
import { useStyles } from './styles';

export interface ConversationListProps {
  /** Callback when conversation is selected */
  onSelect?: (conversationId: string) => void;
  /** Callback when new conversation is created */
  onNew?: () => void;
  /** Callback when conversation is deleted */
  onDelete?: (conversationId: string) => void;
  /** Callback to toggle sidebar visibility */
  onToggleSidebar?: () => void;
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
  className,
}: ConversationListProps) {
  const { styles, cx } = useStyles();

  const conversations = useConversationStore((state) => state.conversations);
  const activeId = useConversationStore((state) => state.activeConversationId);
  const isLoading = useConversationStore((state) => state.isLoading);
  const streamingTitles = useConversationStore((state) => state.streamingTitles);

  const handleNew = useCallback(async () => {
    // We don't create a conversation in DB yet (Lazy creation)
    // Just trigger the callback to reset the UI
    onNew?.();
  }, [onNew]);

  const handleSelect = useCallback(
    async (id: string) => {
      await switchConversation(id);
      onSelect?.(id);
    },
    [onSelect]
  );

  const handleDelete = useCallback(
    async (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      await deleteConversationService(id);
      onDelete?.(id);
    },
    [onDelete]
  );

  /**
   * Group conversations by date
   */
  const groupedConversations = useMemo(() => {
    const groups: { [key: string]: typeof conversations } = {
      今天: [],
      昨天: [],
      過去七天: [],
      更早以前: [],
    };

    const now = new Date();
    now.setHours(0, 0, 0, 0);

    conversations.forEach((conv) => {
      const date = new Date(conv.updatedAt);
      date.setHours(0, 0, 0, 0);
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

      if (diffDays === 0) groups['今天'].push(conv);
      else if (diffDays === 1) groups['昨天'].push(conv);
      else if (diffDays < 7) groups['過去七天'].push(conv);
      else groups['更早以前'].push(conv);
    });

    return Object.entries(groups).filter(([, items]) => items.length > 0);
  }, [conversations]);

  return (
    <div className={cx(styles.container, className)}>
      {/* Logo & Toggle Area */}
      <div className={styles.logoContainer}>
        <div className={styles.logoWrapper}>
          <Image 
            src="/logo/complteLogo_03_whiteText.png" 
            alt="XiaoHong Logo" 
            width={160} 
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
              {items.map((conv) => (
                <div
                  key={conv.id}
                  className={cx(
                    styles.item,
                    conv.id === activeId && styles.itemActive
                  )}
                  onClick={() => handleSelect(conv.id)}
                >
                  <MessageSquare size={16} className={styles.itemIcon} />
                  <div className={styles.itemContent}>
                    <span className={cx(styles.itemTitle, 'conv-title')}>
                      {streamingTitles[conv.id] !== undefined ? (
                        <>
                          {streamingTitles[conv.id]}
                          <span className={styles.cursor} />
                        </>
                      ) : (
                        conv.title || '新對話'
                      )}
                    </span>
                  </div>
                  <button
                    className={cx(styles.deleteBtn, 'delete-btn')}
                    onClick={(e) => handleDelete(conv.id, e)}
                    title="刪除對話"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </React.Fragment>
          ))
        )}
      </div>
    </div>
  );
}
