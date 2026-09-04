import { describe, expect, it } from 'vitest';
import type { DisplayMessage } from '@/store/chat';
import {
  selectLiveTutorConversationId,
  selectLiveTutorMessages,
} from '@/components/LiveTutor/session';

function message(conversationId: string, content: string): DisplayMessage {
  return {
    id: `${conversationId}-${content}`,
    userId: 'user-1',
    conversationId,
    role: 'user',
    content,
    createdAt: new Date(),
  };
}

describe('Live Tutor session binding', () => {
  it('leaves a new empty voice session unbound until speech produces a message', () => {
    expect(selectLiveTutorConversationId(null, [])).toBeNull();
  });

  it('always prefers the currently active conversation over previously rendered messages', () => {
    expect(selectLiveTutorConversationId('conversation-current', [
      message('conversation-stale', 'old'),
    ])).toBe('conversation-current');
  });

  it('uses the latest rendered conversation during a selection handoff', () => {
    expect(selectLiveTutorConversationId(null, [
      message('conversation-old', 'old'),
      message('conversation-current', 'current'),
    ])).toBe('conversation-current');
  });

  it('never leaks messages from another conversation into realtime context', () => {
    const current = message('conversation-current', 'current');
    expect(selectLiveTutorMessages([
      message('conversation-stale', 'old'),
      current,
    ], 'conversation-current')).toEqual([current]);
  });
});
