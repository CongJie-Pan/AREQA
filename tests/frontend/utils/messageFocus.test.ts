import { afterEach, describe, expect, it } from 'vitest';
import { consumeSourceMessageFocus, requestSourceMessageFocus } from '@/utils/messageFocus';

describe('messageFocus utilities', () => {
  afterEach(() => {
    window.sessionStorage.clear();
  });

  it('stores and consumes a pending source message focus for the matching conversation', () => {
    requestSourceMessageFocus('conversation-1', 'message-1');

    expect(consumeSourceMessageFocus('conversation-1')).toBe('message-1');
    expect(consumeSourceMessageFocus('conversation-1')).toBeNull();
  });

  it('keeps a pending source focus when a different conversation is rendered first', () => {
    requestSourceMessageFocus('conversation-1', 'message-1');

    expect(consumeSourceMessageFocus('conversation-2')).toBeNull();
    expect(consumeSourceMessageFocus('conversation-1')).toBe('message-1');
  });
});
