import { describe, expect, it } from 'vitest';
import { shouldDelegateEnglishSpeakingTurn, shouldDelegateVoiceTurnToDeepAnswer } from '@/services/realtime/deepDelegation';

describe('shouldDelegateVoiceTurnToDeepAnswer', () => {
  it('routes detailed document and paper questions to the backend depth pipeline', () => {
    expect(shouldDelegateVoiceTurnToDeepAnswer('請詳細解釋這篇論文的方法')).toBe(true);
    expect(shouldDelegateVoiceTurnToDeepAnswer('Can you compare the paper methodology with the baseline?')).toBe(true);
  });

  it('keeps greetings and short acknowledgements in the live voice model', () => {
    expect(shouldDelegateVoiceTurnToDeepAnswer('你好')).toBe(false);
    expect(shouldDelegateVoiceTurnToDeepAnswer('ok')).toBe(false);
  });
});

describe('shouldDelegateEnglishSpeakingTurn', () => {
  it('routes transcript practice and subsequent answers through the backend', () => {
    expect(shouldDelegateEnglishSpeakingTurn('我給你了一個對話的逐字稿，想依此練習托福英文口說', false)).toBe(true);
    expect(shouldDelegateEnglishSpeakingTurn('The student disagrees because the plan is expensive.', true)).toBe(true);
    expect(shouldDelegateEnglishSpeakingTurn('你好', false)).toBe(false);
    expect(shouldDelegateEnglishSpeakingTurn('停止練習', true)).toBe(false);
  });
});
