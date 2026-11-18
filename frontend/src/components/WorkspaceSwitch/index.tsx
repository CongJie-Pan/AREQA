'use client';

/**
 * WorkspaceSwitch
 *
 * Switches between ordinary Chat and the Topic Finder (選題) workspace. The
 * sidebar shows the compact icon variant at all times; the empty new-chat screen
 * shows the labelled segmented variant. Both read and write the same
 * conversation-store workspace, so they can never disagree.
 */

import React, { useCallback } from 'react';
import { MessageSquare, Telescope } from 'lucide-react';
import type { ConversationKind } from '@/database/schema';
import { useConversationStore } from '@/store/conversation';
import { useChatStore, chatSelectors } from '@/store/chat';
import { useLiveTutorStore } from '@/store/liveTutor';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { conversationKindOf } from '@/utils/conversationKind';

export interface WorkspaceSwitchProps {
  /** `icons` for the sidebar header, `segmented` for the empty new-chat screen. */
  variant: 'icons' | 'segmented';
  /**
   * Called when switching away from an open conversation of the other kind.
   * Defaults to clearing the active conversation so the new workspace's home shows.
   */
  onLeaveConversation?: () => void;
  className?: string;
}

const OPTIONS: { kind: ConversationKind; Icon: typeof MessageSquare; label: 'workspaceChat' | 'workspaceTopicFinder'; tooltip: 'workspaceChatTooltip' | 'workspaceTopicFinderTooltip' }[] = [
  { kind: 'chat', Icon: MessageSquare, label: 'workspaceChat', tooltip: 'workspaceChatTooltip' },
  { kind: 'research_coach', Icon: Telescope, label: 'workspaceTopicFinder', tooltip: 'workspaceTopicFinderTooltip' },
];

function leaveToHome(): void {
  useConversationStore.getState().clearActiveConversation();
  useChatStore.getState().clearMessages();
  useChatStore.getState().resetStreamingState();
}

export function WorkspaceSwitch({ variant, onLeaveConversation, className }: WorkspaceSwitchProps) {
  const { t } = useUserPreferences();
  const workspace = useConversationStore((state) => state.workspace);

  const select = useCallback((kind: ConversationKind) => {
    const state = useConversationStore.getState();
    if (kind === state.workspace) return;
    const active = state.conversations.find((conversation) => conversation.id === state.activeConversationId);
    state.setWorkspace(kind);
    // Live voice is a Chat feature; it does not carry into Topic Finder.
    if (kind === 'research_coach' && useLiveTutorStore.getState().isOpen) useLiveTutorStore.getState().requestClose();
    // An open conversation of the other kind cannot stay on screen: its workspace is fixed.
    if (state.activeConversationId && (!active || conversationKindOf(active) !== kind)) {
      (onLeaveConversation ?? leaveToHome)();
    }
  }, [onLeaveConversation]);

  return (
    <div
      role="group"
      aria-label={t('workspaceSwitch')}
      className={['areqa-workspace-switch', `areqa-workspace-switch-${variant}`, className].filter(Boolean).join(' ')}
    >
      {OPTIONS.map(({ kind, Icon, label, tooltip }) => (
        <button
          key={kind}
          type="button"
          className="areqa-workspace-switch-option"
          aria-pressed={workspace === kind}
          aria-label={variant === 'icons' ? t(tooltip) : undefined}
          title={t(tooltip)}
          data-workspace={kind}
          onClick={() => select(kind)}
        >
          <Icon size={variant === 'icons' ? 16 : 15} aria-hidden="true" />
          {variant === 'segmented' && <span>{t(label)}</span>}
        </button>
      ))}
    </div>
  );
}

/**
 * Segmented switch for the empty new-chat screen, pinned to the top of the chat area.
 * It disappears once the conversation has a message, because a conversation's kind is fixed.
 */
export function HomeWorkspaceSwitch() {
  const isEmpty = useChatStore((state) => chatSelectors.displayMessages(state).length === 0);
  if (!isEmpty) return null;
  return (
    <div className="areqa-workspace-switch-home-slot">
      <WorkspaceSwitch variant="segmented" />
    </div>
  );
}

export default WorkspaceSwitch;
