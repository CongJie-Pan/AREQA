import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/authenticatedFetch', () => ({
  authenticatedFetch: vi.fn(),
}));

import { authenticatedFetch } from '@/services/authenticatedFetch';
import { createReadAloudAudio, prepareReadAloudText } from '@/services/speech/readAloud';

describe('readAloud speech service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizes markdown into readable text', () => {
    expect(prepareReadAloudText('## 重點\n\n請讀 **這段** [內容](https://example.com)。')).toBe('重點\n\n請讀 這段 內容。');
  });

  it('posts readable text to the configured speech endpoint', async () => {
    const signal = new AbortController().signal;
    vi.mocked(authenticatedFetch).mockResolvedValue(
      new Response(new Blob(['audio'], { type: 'audio/mpeg' }), { status: 200 }),
    );

    await createReadAloudAudio('請讀 **這段**', signal);

    expect(authenticatedFetch).toHaveBeenCalledWith('/api/speech/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: '請讀 這段' }),
      signal,
    });
  });
});
