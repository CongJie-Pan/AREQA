'use client';

/**
 * Chat row menu shared by the sidebar and the project page:
 * 釘選 / 重新命名 / 加入專案 (or 更換專案) › / 從專案中移除 / … / 刪除.
 *
 * Callers render the Dropdown and pass extra items (e.g. sidebar branch links);
 * this hook owns the menu items, the click handling, and the dialogs those
 * actions open (rename, create project from the submenu).
 */

import React, { useCallback, useState } from 'react';
import { App, Input, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { FolderMinus, Pencil, Pin, PinOff, Plus, Trash2 } from 'lucide-react';
import type { Conversation } from '@/database/schema';
import { ProjectFormModal } from '@/components/Projects/ProjectFormModal';
import { ProjectIcon } from '@/components/Projects/ProjectIcon';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { deleteConversation as deleteConversationService } from '@/services/chat';
import { databaseService } from '@/services/database';
import { useAuthStore } from '@/store/auth';
import { useConversationStore } from '@/store/conversation';
import { usePinnedConversationStore } from '@/store/pinnedConversations';
import { useProjectStore } from '@/store/projects';
import { logger } from '@/utils/logger';

type MenuItem = NonNullable<MenuProps['items']>[number];

export interface ConversationMenuOptions {
  /** Close the open menu (the submenu search closes it on Enter). */
  closeMenu: () => void;
  onDeleted?: (conversationId: string) => void;
}

export function menuLabel(icon: React.ReactNode, label: string) {
  return <span className="areqa-conversation-menu-label">{icon}<span>{label}</span></span>;
}

export function useConversationMenu({ closeMenu, onDeleted }: ConversationMenuOptions) {
  const { message } = App.useApp();
  const { t } = useUserPreferences();
  const isSignedIn = useAuthStore((state) => Boolean(state.user));
  const projects = useProjectStore((state) => state.projects);
  const pinnedIds = usePinnedConversationStore((state) => state.ids);
  const [projectQuery, setProjectQuery] = useState('');
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const [createFor, setCreateFor] = useState<string | null>(null);

  const assignProject = useCallback(async (conversationId: string, projectId: string | null) => {
    try {
      await databaseService.conversation.update(conversationId, { projectId });
      useConversationStore.getState().updateConversation(conversationId, { projectId, updatedAt: new Date() });
      const project = projectId ? useProjectStore.getState().projects.find((item) => item.id === projectId) : null;
      logger.info('conversation_project_assigned', { component: 'ConversationMenu', conversationId, projectId });
      message.success(project ? t('projectAddedTo', { name: project.name }) : t('projectRemoved'));
    } catch {
      message.error(t('projectSaveFailed'));
    }
  }, [message, t]);

  const createAndAssign = useCallback(async (conversationId: string, name: string) => {
    try {
      const project = await useProjectStore.getState().create(name);
      await assignProject(conversationId, project.id);
    } catch {
      message.error(t('projectSaveFailed'));
    }
  }, [assignProject, message, t]);

  /** "加入專案 / 更換專案" flyout: search or create, then the other projects (image 07). */
  const projectSubmenu = (conv: Conversation): MenuItem => {
    const query = projectQuery.trim();
    const needle = query.toLocaleLowerCase();
    const matches = projects.filter((project) => project.id !== conv.projectId
      && (!needle || project.name.toLocaleLowerCase().includes(needle)));
    const exact = projects.some((project) => project.name.toLocaleLowerCase() === needle);
    return {
      key: 'project',
      label: menuLabel(<ProjectIcon size={14} />, t(conv.projectId ? 'projectChange' : 'projectAddTo')),
      popupClassName: 'areqa-project-submenu',
      children: [
        {
          key: 'project-search',
          className: 'areqa-project-submenu-search',
          label: (
            <input
              className="areqa-project-submenu-input"
              value={projectQuery}
              maxLength={120}
              placeholder={t('projectSearchOrCreate')}
              aria-label={t('projectSearchOrCreate')}
              onChange={(event) => setProjectQuery(event.target.value)}
              onClick={(event) => event.stopPropagation()}
              // Typing must not drive the menu's own keyboard navigation.
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === 'Enter') {
                  closeMenu();
                  setProjectQuery('');
                  if (matches.length === 1 && query) void assignProject(conv.id, matches[0].id);
                  else if (query && !exact) void createAndAssign(conv.id, query);
                }
              }}
            />
          ),
        },
        {
          key: 'project-new',
          label: menuLabel(<Plus size={14} />, query && !exact ? t('projectCreateNamed', { name: query }) : t('projectNew')),
        },
        { type: 'divider' },
        ...matches.map((project) => ({ key: `project:${project.id}`, label: project.name, title: project.name })),
      ],
    };
  };

  /** Menu items for one chat; `extra` goes after the project items, before Delete. */
  const itemsFor = (conv: Conversation, extra: MenuItem[] = []): MenuProps['items'] => {
    const isPinned = pinnedIds.includes(conv.id);
    return [
      { key: 'pin', label: menuLabel(isPinned ? <PinOff size={14} /> : <Pin size={14} />, t(isPinned ? 'unpin' : 'pin')) },
      { key: 'rename', label: menuLabel(<Pencil size={14} />, t('rename')) },
      ...(isSignedIn && !conv.collaboration ? [
        projectSubmenu(conv),
        ...(conv.projectId ? [{
          key: 'project-remove', label: menuLabel(<FolderMinus size={14} />, t('projectRemoveFrom')),
        }] : []),
      ] : []),
      ...extra,
      { type: 'divider' },
      { key: 'delete', danger: true, label: menuLabel(<Trash2 size={14} />, t('delete')) },
    ];
  };

  /**
   * Run a menu action. Returns false for keys this hook does not own (callers
   * handle those) and for the search field, which keeps the menu open.
   */
  const handleKey = (conv: Conversation, key: string, displayTitle: string): boolean => {
    if (key === 'project-search') return false;
    if (key === 'pin') usePinnedConversationStore.getState().toggle(conv.id);
    else if (key === 'rename') {
      setRenameTarget({ id: conv.id, title: displayTitle });
      setRenameValue(displayTitle);
    } else if (key.startsWith('project:')) void assignProject(conv.id, key.slice('project:'.length));
    else if (key === 'project-new') {
      const query = projectQuery.trim();
      if (query && !projects.some((project) => project.name.toLocaleLowerCase() === query.toLocaleLowerCase())) {
        void createAndAssign(conv.id, query);
      } else {
        setCreateFor(conv.id);
      }
    } else if (key === 'project-remove') void assignProject(conv.id, null);
    else if (key === 'delete') {
      void deleteConversationService(conv.id).then(() => {
        usePinnedConversationStore.getState().remove(conv.id);
        onDeleted?.(conv.id);
      });
    } else return false;
    setProjectQuery('');
    return true;
  };

  const closeRename = () => {
    if (isRenaming) return;
    setRenameTarget(null);
    setRenameValue('');
  };

  const submitRename = async () => {
    if (!renameTarget) return;
    const nextTitle = renameValue.trim();
    if (!nextTitle) {
      message.warning(t('enterConversationName'));
      return;
    }
    setIsRenaming(true);
    try {
      await databaseService.conversation.update(renameTarget.id, { title: nextTitle });
      useConversationStore.getState().updateConversation(renameTarget.id, { title: nextTitle, updatedAt: new Date() });
      message.success(t('renameSuccess'));
      setRenameTarget(null);
      setRenameValue('');
    } catch {
      message.error(t('renameFailed'));
    } finally {
      setIsRenaming(false);
    }
  };

  const dialogs = (
    <>
      <Modal
        confirmLoading={isRenaming}
        okButtonProps={{ disabled: !renameValue.trim() }}
        okText={t('save')}
        onCancel={closeRename}
        onOk={() => { void submitRename(); }}
        open={renameTarget !== null}
        title={t('renameTitle')}
      >
        <Input
          autoFocus
          maxLength={80}
          onChange={(event) => setRenameValue(event.target.value)}
          onPressEnter={() => { void submitRename(); }}
          placeholder={t('renamePlaceholder')}
          value={renameValue}
        />
      </Modal>
      <ProjectFormModal
        open={createFor !== null}
        onClose={() => setCreateFor(null)}
        onSubmit={async ({ name, description }) => {
          const target = createFor;
          const project = await useProjectStore.getState().create(name, description);
          if (target) await assignProject(target, project.id);
        }}
      />
    </>
  );

  return { itemsFor, handleKey, dialogs, pinnedIds, resetProjectQuery: () => setProjectQuery('') };
}
