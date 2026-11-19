import { useCallback, useEffect, useState } from 'react';
import { authenticatedFetch } from '@/services/authenticatedFetch';
import { logger } from '@/utils/logger';
import type { ShareAccessLevel, ShareMember } from './SharePanel';

interface ShareAccessState {
  accessLevel: ShareAccessLevel;
  hasLink: boolean;
  members: ShareMember[];
}

const INITIAL_STATE: ShareAccessState = { accessLevel: 'view', hasLink: false, members: [] };

/**
 * Owner-side link access for the share panel.
 *
 * Loads the current access level (and participants for edit links) when the
 * panel opens. Failures keep the panel usable as a plain view-only share.
 */
export function useShareAccess(conversationId: string | null, open: boolean) {
  const [state, setState] = useState<ShareAccessState>(INITIAL_STATE);

  const loadMembers = useCallback(async (id: string): Promise<ShareMember[]> => {
    try {
      const response = await authenticatedFetch(`/api/collab/conversations/${id}/members`);
      if (!response.ok) return [];
      const payload = await response.json() as { members?: ShareMember[] };
      return Array.isArray(payload.members) ? payload.members : [];
    } catch {
      return [];
    }
  }, []);

  useEffect(() => {
    if (!open || !conversationId) return undefined;
    let active = true;
    void (async () => {
      try {
        const response = await authenticatedFetch(`/api/share/conversations/${conversationId}`);
        const payload = response.ok
          ? await response.json() as { hasLink?: boolean; accessLevel?: string }
          : {};
        const accessLevel: ShareAccessLevel = payload.accessLevel === 'edit' ? 'edit' : 'view';
        const members = accessLevel === 'edit' ? await loadMembers(conversationId) : [];
        if (!active) return;
        setState({ accessLevel, hasLink: Boolean(payload.hasLink), members });
      } catch {
        if (!active) return;
        logger.warn('share_access_load_failed', { component: 'SharePanel', conversationId });
        setState(INITIAL_STATE);
      }
    })();
    return () => { active = false; };
  }, [conversationId, loadMembers, open]);

  /** Record the access the server just applied for this link. */
  const markApplied = useCallback((accessLevel: ShareAccessLevel) => {
    setState((current) => ({ ...current, accessLevel, hasLink: true }));
    if (accessLevel === 'edit' && conversationId) {
      void loadMembers(conversationId).then((members) => setState((current) => ({ ...current, members })));
    }
  }, [conversationId, loadMembers]);

  const setAccessLevel = useCallback((accessLevel: ShareAccessLevel) => {
    setState((current) => ({ ...current, accessLevel }));
  }, []);

  const removeMember = useCallback(async (userId: string): Promise<boolean> => {
    if (!conversationId) return false;
    const response = await authenticatedFetch(
      `/api/collab/conversations/${conversationId}/members?userId=${encodeURIComponent(userId)}`,
      { method: 'DELETE' },
    ).catch(() => null);
    if (!response?.ok) return false;
    setState((current) => ({ ...current, members: current.members.filter((member) => member.userId !== userId) }));
    return true;
  }, [conversationId]);

  return { ...state, setAccessLevel, markApplied, removeMember };
}
