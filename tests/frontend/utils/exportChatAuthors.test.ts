import { afterEach, describe, expect, it, vi } from 'vitest';

const { saveAs } = vi.hoisted(() => ({ saveAs: vi.fn() }));
// exportChat resolves the package from frontend/node_modules; mock that copy.
vi.mock('../../../frontend/node_modules/file-saver', () => ({ saveAs, default: { saveAs } }));

import { exportToMarkdown } from '@/utils/exportChat';
import type { DisplayMessage } from '@/store/chat/types';

const messages = [
  { id: 'q1', role: 'user', content: 'owner question', author: { userId: 'owner', name: 'Jay' } },
  { id: 'a1', role: 'assistant', content: 'answer' },
  { id: 'q2', role: 'user', content: 'member question', author: { userId: 'mei', name: 'Mei' } },
] as unknown as DisplayMessage[];

async function exportedText(): Promise<string> {
  const blob = saveAs.mock.calls[0][0] as Blob;
  // jsdom's Blob has no text(); FileReader is available.
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });
}

describe('exportToMarkdown speaker names', () => {
  afterEach(() => saveAs.mockReset());

  it('keeps "您" for ordinary chats', async () => {
    exportToMarkdown(messages);
    const text = await exportedText();
    expect(text.match(/### 👤 您/g)).toHaveLength(2);
    expect(text).toContain('### 🤖 AREQA');
  });

  it('names each asker in shared chats', async () => {
    exportToMarkdown(messages, { userLabel: (message) => message.author?.name ?? '參與者' });
    const text = await exportedText();
    expect(text).toContain('### 👤 Jay\nowner question');
    expect(text).toContain('### 👤 Mei\nmember question');
    expect(text).not.toContain('👤 您');
  });
});
