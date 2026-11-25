/**
 * Pinned conversations: a local UI preference shared by the sidebar and the
 * project page, so pinning a chat anywhere updates the sidebar at once.
 * Stored under the key the sidebar has always used; storage failures never
 * block chat usage.
 */

import { create } from 'zustand';

export const PINNED_CONVERSATION_IDS_KEY = 'areqa:pinned-conversation-ids';

interface PinnedConversationsState {
  ids: string[];
  /** True once stored ids were read; later growth means the learner pinned something. */
  hydrated: boolean;
  /** Read the stored ids; called on the client after mount to avoid hydration mismatches. */
  hydrate: () => void;
  toggle: (id: string) => void;
  remove: (id: string) => void;
}

function persist(ids: string[]) {
  try {
    window.localStorage.setItem(PINNED_CONVERSATION_IDS_KEY, JSON.stringify(ids));
  } catch {
    // Pinning is a local UI preference. Storage failures should not block chat usage.
  }
}

export const usePinnedConversationStore = create<PinnedConversationsState>((set, get) => ({
  ids: [],
  hydrated: false,
  hydrate: () => {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(PINNED_CONVERSATION_IDS_KEY) ?? '[]');
      set({ ids: Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : [], hydrated: true });
    } catch {
      set({ ids: [], hydrated: true });
    }
  },
  toggle: (id) => {
    const current = get().ids;
    const ids = current.includes(id) ? current.filter((pinnedId) => pinnedId !== id) : [id, ...current];
    set({ ids });
    persist(ids);
  },
  remove: (id) => {
    if (!get().ids.includes(id)) return;
    const ids = get().ids.filter((pinnedId) => pinnedId !== id);
    set({ ids });
    persist(ids);
  },
}));
