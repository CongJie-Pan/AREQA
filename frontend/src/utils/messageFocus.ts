const PENDING_SOURCE_MESSAGE_FOCUS_KEY = 'areqa:pending-source-message-focus';

interface PendingSourceMessageFocus {
  conversationId: string;
  messageId: string;
}

function isPendingSourceMessageFocus(value: unknown): value is PendingSourceMessageFocus {
  return (
    typeof value === 'object'
    && value !== null
    && typeof (value as PendingSourceMessageFocus).conversationId === 'string'
    && typeof (value as PendingSourceMessageFocus).messageId === 'string'
  );
}

export function requestSourceMessageFocus(conversationId: string, messageId: string) {
  if (typeof window === 'undefined') return;

  try {
    window.sessionStorage.setItem(
      PENDING_SOURCE_MESSAGE_FOCUS_KEY,
      JSON.stringify({ conversationId, messageId }),
    );
  } catch {
    // Focusing the source message is a convenience path; opening the conversation still works without storage.
  }
}

export function consumeSourceMessageFocus(conversationId: string) {
  if (typeof window === 'undefined') return null;

  try {
    const rawValue = window.sessionStorage.getItem(PENDING_SOURCE_MESSAGE_FOCUS_KEY);
    if (!rawValue) return null;

    const parsedValue: unknown = JSON.parse(rawValue);
    if (!isPendingSourceMessageFocus(parsedValue)) {
      window.sessionStorage.removeItem(PENDING_SOURCE_MESSAGE_FOCUS_KEY);
      return null;
    }

    if (parsedValue.conversationId !== conversationId) return null;

    window.sessionStorage.removeItem(PENDING_SOURCE_MESSAGE_FOCUS_KEY);
    return parsedValue.messageId;
  } catch {
    window.sessionStorage.removeItem(PENDING_SOURCE_MESSAGE_FOCUS_KEY);
    return null;
  }
}
