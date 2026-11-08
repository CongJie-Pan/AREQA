import { describe, expect, it } from 'vitest';
import { validateMessagesArray } from '@/utils/validation';

describe('long conversation transport validation', () => {
  it.each([99, 100, 101, 201])('accepts %i ordinary messages', (count) => {
    expect(validateMessagesArray(Array.from({ length: count }, () => ({ role: 'user', content: 'hello' })))).toEqual({ valid: true });
  });
  it('rejects non-serializable data without throwing', () => {
    expect(validateMessagesArray([{ role: 'user', content: 'hi', extra: BigInt(1) }]).valid).toBe(false);
  });
  it('rejects oversized total history', () => {
    expect(validateMessagesArray(Array.from({ length: 100 }, () => ({ role: 'user', content: '中'.repeat(30_000) }))).valid).toBe(false);
  });
});
