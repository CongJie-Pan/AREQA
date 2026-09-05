import { describe, expect, it } from 'vitest';
import { buildRealtimeContext } from '@/services/realtime/context';
import { normalizeVoiceTranscript } from '@/services/realtime/language';
import type { DisplayMessage } from '@/store/chat';

describe('shared voice context', () => {
  it('keeps the original paper discussion alongside recent turns within a bounded budget', () => {
    const messages: DisplayMessage[] = Array.from({ length: 40 }, (_, index) => ({
      id: `m${index}`, conversationId: 'conversation', userId: 'guest',
      role: index % 2 ? 'assistant' : 'user', createdAt: new Date(index),
      content: `Turn ${index}: ${'context '.repeat(1200)} END ${index}`,
      ...(index === 0 ? { attachments: [{ name: 'paper.pdf', mediaType: 'application/pdf', sizeBytes: 1 }] } : {}),
    }));
    const snapshot = buildRealtimeContext(messages);
    expect(snapshot).toHaveLength(24);
    expect(snapshot[0].id).toBe('m0');
    expect(snapshot[1].id).toBe('m1');
    expect(snapshot.at(-1)?.id).toBe('m39');
    expect(snapshot[0].content).toContain('paper.pdf');
    expect(snapshot[0].content).toContain('END 0');
    expect(snapshot.reduce((sum, message) => sum + message.content.length, 0)).toBeLessThanOrEqual(48000);
    expect(snapshot.every((message) => message.content.length <= 6000)).toBe(true);
  });

  it('normalizes speech to Traditional Chinese without translating English', () => {
    expect(normalizeVoiceTranscript('请解释这篇论文的研究方法与结论。OpenAI API', 'zh-TW'))
      .toBe('請解釋這篇論文的研究方法與結論。OpenAI API');
    expect(normalizeVoiceTranscript('请解释论文', 'en')).toBe('請解釋論文');
    expect(normalizeVoiceTranscript('请解释论文', 'zh-CN')).toBe('请解释论文');
  });
});
