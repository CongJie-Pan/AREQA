import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const replace = vi.fn();
const authState = { user: null as null | { id: string }, isInitialized: true };
vi.mock('@/store/auth', () => ({
  initializeAuth: vi.fn(async () => undefined),
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

import { SharedConversationView } from '../../../../frontend/src/app/share/[token]/SharedConversationView';
import { toSharedDisplayMessages, type SharedConversation } from '../../../../frontend/src/components/SharedConversation';
import { UserPreferencesProvider } from '../../../../frontend/src/contexts/UserPreferencesContext';

const conversation: SharedConversation = {
  id: 'conversation-1',
  title: '學習理論',
  createdAt: '2026-11-15T00:00:00.000Z',
  updatedAt: '2026-11-15T00:00:00.000Z',
  sharedAt: '2026-11-15T01:00:00.000Z',
  messages: [
    {
      id: 'user-1', role: 'user', content: '請說明這份 PDF', createdAt: '2026-11-15T00:00:00.000Z',
      attachments: [{ name: 'Ch08.pdf', mediaType: 'application/pdf', sizeBytes: 10, preview: { dataUrl: 'data:image/jpeg;base64,/9j/', width: 400, height: 300 } }],
    },
    {
      id: 'assistant-1', role: 'assistant', createdAt: '2026-11-15T00:00:01.000Z',
      content: ['### 1. 研究動機與目的', '', '- 第一點', '- 第二點', '', '| 指標 | 值 |', '| --- | --- |', '| 準確率 | 98% |'].join('\n'),
      stoppedByUser: true,
    },
  ],
};

const renderView = (token?: string) => render(
  <UserPreferencesProvider><SharedConversationView conversation={conversation} token={token} /></UserPreferencesProvider>,
);

describe('SharedConversationView', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('areqa:interface-language', 'zh-TW');
    replace.mockReset();
    authState.user = null;
    Object.defineProperty(window, 'location', { value: { ...window.location, replace }, writable: true });
  });

  it('renders shared messages with the chat renderer (headings, lists, tables, attachments, stopped notice)', async () => {
    renderView('L-GIo3nG6ceEijhdinSsm3A3');

    await waitFor(() => expect(screen.getByRole('heading', { name: '1. 研究動機與目的', level: 3 })).toBeInTheDocument());
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(expect.arrayContaining(['第一點', '第二點']));
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽 Ch08.pdf' })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('你停止了 AREQA 的回應');
    expect(replace).not.toHaveBeenCalled();
  });

  it('never offers editing or feedback on the public copy', () => {
    renderView('L-GIo3nG6ceEijhdinSsm3A3');
    expect(screen.queryByRole('button', { name: /重新生成|有幫助|編輯/ })).not.toBeInTheDocument();
  });

  it('moves a signed-in visitor into their own workspace view', async () => {
    authState.user = { id: 'viewer' };
    renderView('L-GIo3nG6ceEijhdinSsm3A3');
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/?share=L-GIo3nG6ceEijhdinSsm3A3'));
  });
});

describe('toSharedDisplayMessages', () => {
  it('maps share payload rows onto chat messages and drops unsafe attachment data', () => {
    const [user, assistant] = toSharedDisplayMessages({
      ...conversation,
      messages: [
        { ...conversation.messages[0], attachments: [{ name: 'x.png', mediaType: 'image/png', sizeBytes: 1, preview: { dataUrl: 'https://evil.example/x.png', width: 10, height: 10 } }] },
        { ...conversation.messages[1], answerBlocks: null, stoppedByUser: false },
      ],
    });

    expect(user.attachments?.[0]).toEqual({ name: 'x.png', mediaType: 'image/png', sizeBytes: 1 });
    expect(user.createdAt).toBeInstanceOf(Date);
    expect(assistant).not.toHaveProperty('answerBlocks');
    expect(assistant).not.toHaveProperty('stoppedByUser');
  });
});
