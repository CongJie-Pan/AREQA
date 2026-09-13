import { describe, expect, it } from 'vitest';
import { normalizeReadbackText } from '@/services/realtime/readbackText';

describe('normalizeReadbackText', () => {
  it('converts markdown-rich answers into deterministic plain readback text', () => {
    const text = normalizeReadbackText([
      '### 第一步：特徵提取（Feature Extraction）',
      '',
      '* **白話直覺**：  ',
      '  拿一張客觀的**「體檢清單」**，要 AI 逐項檢查並打勾 🎯。',
      '',
      '---',
      '',
      '詳見 [OpenAI](https://example.com) 與 `$Q_1 \\sim Q_8$`。',
    ].join('\n'));

    expect(text).toBe([
      '第一步：特徵提取（Feature Extraction）',
      '白話直覺：',
      '拿一張客觀的「體檢清單」，要 AI 逐項檢查並打勾 。',
      '',
      '詳見 OpenAI 與 Q_1 \\sim Q_8。',
    ].join('\n'));
  });
});
