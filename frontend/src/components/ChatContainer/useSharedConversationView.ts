import { useCallback, useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import type { SharedConversation } from '@/components/SharedConversation';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';

const SHARE_TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,80}$/;
const SHARE_PARAM = 'share';

export interface SharedViewState {
  token: string;
  conversation: SharedConversation;
  /** True when the signed-in viewer created this share. */
  isOwner: boolean;
  /** Original conversation id; only returned to the owner. */
  conversationId?: string;
}

function removeShareParam(): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has(SHARE_PARAM)) return;
  url.searchParams.delete(SHARE_PARAM);
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
}

/**
 * Open a shared conversation (`/?share=<token>`) read-only inside the
 * signed-in workspace.
 *
 * Signed-out visitors go back to the public `/share/<token>` page. Ownership is
 * resolved by the server with the viewer's own session.
 */
export function useSharedConversationView(
  user: User | null,
  isAuthReady: boolean,
  onUnavailable: () => void,
): { sharedView: SharedViewState | null; exitSharedView: () => void } {
  const [sharedView, setSharedView] = useState<SharedViewState | null>(null);
  const userId = user?.id ?? null;

  useEffect(() => {
    if (!isAuthReady) return undefined;
    const token = new URL(window.location.href).searchParams.get(SHARE_PARAM) ?? '';
    if (!SHARE_TOKEN_PATTERN.test(token)) return undefined;
    if (!userId) {
      window.location.replace(`/share/${encodeURIComponent(token)}`);
      return undefined;
    }

    let active = true;
    void (async () => {
      const [conversationResponse, viewerResponse] = await Promise.all([
        fetch(`/api/share/${encodeURIComponent(token)}`),
        authenticatedFetch(`/api/share/${encodeURIComponent(token)}/viewer`).catch(() => null),
      ]);
      if (!active) return;
      if (!conversationResponse.ok) {
        logger.warn('share_view_unavailable', { component: 'ChatContainer', status: conversationResponse.status });
        removeShareParam();
        onUnavailable();
        return;
      }
      const conversation = await conversationResponse.json() as SharedConversation;
      const viewer = viewerResponse?.ok
        ? await viewerResponse.json() as { isOwner?: boolean; conversationId?: string }
        : { isOwner: false };
      if (!active) return;
      logger.info('share_view_opened', { component: 'ChatContainer', isOwner: Boolean(viewer.isOwner) });
      setSharedView({
        token,
        conversation,
        isOwner: Boolean(viewer.isOwner),
        ...(viewer.isOwner && viewer.conversationId ? { conversationId: viewer.conversationId } : {}),
      });
    })().catch(() => {
      if (!active) return;
      removeShareParam();
      onUnavailable();
    });
    return () => { active = false; };
  }, [isAuthReady, onUnavailable, userId]);

  const exitSharedView = useCallback(() => {
    setSharedView(null);
    removeShareParam();
  }, []);

  return { sharedView, exitSharedView };
}
