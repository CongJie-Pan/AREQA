import { describe, expect, it } from 'vitest';
import {
  conversationKindOf,
  isTopicFinderConversation,
  normalizeConversationKind,
  resolveConversationKind,
} from '@/utils/conversationKind';
import type { Conversation } from '@/database/schema';

const conversation = (id: string, kind?: Conversation['kind']): Conversation => ({
  id, userId: 'u', title: id, createdAt: new Date(0), updatedAt: new Date(0), messageCount: 0, lastMessagePreview: '',
  ...(kind ? { kind } : {}),
});

describe('conversation kind helpers', () => {
  it.each([
    ['research_coach', 'research_coach'],
    ['chat', 'chat'],
    [undefined, 'chat'],
    [null, 'chat'],
    ['Research_Coach', 'chat'],
    [7, 'chat'],
  ])('normalizes %s to %s', (raw, expected) => {
    expect(normalizeConversationKind(raw)).toBe(expected);
  });

  it('treats conversations created before Topic Finder as chat', () => {
    expect(conversationKindOf(conversation('legacy'))).toBe('chat');
    expect(isTopicFinderConversation(conversation('legacy'))).toBe(false);
    expect(isTopicFinderConversation(conversation('coach', 'research_coach'))).toBe(true);
    expect(conversationKindOf(undefined)).toBe('chat');
  });

  it('resolves a stored conversation by its own kind, regardless of the visible workspace', () => {
    const state = { conversations: [conversation('coach', 'research_coach'), conversation('chat')], workspace: 'chat' as const };
    expect(resolveConversationKind(state, 'coach')).toBe('research_coach');
    expect(resolveConversationKind({ ...state, workspace: 'research_coach' }, 'chat')).toBe('chat');
  });

  it('falls back to the visible workspace for unsaved conversations and partial state', () => {
    expect(resolveConversationKind({ conversations: [], workspace: 'research_coach' }, 'guest-id')).toBe('research_coach');
    expect(resolveConversationKind({ conversations: [], workspace: 'research_coach' }, null)).toBe('research_coach');
    expect(resolveConversationKind({}, 'anything')).toBe('chat');
  });
});
