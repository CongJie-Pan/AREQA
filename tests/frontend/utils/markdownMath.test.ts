import { describe, expect, it } from 'vitest';
import { normalizeDisplayMathBlocks } from '@/utils/markdownMath';

describe('normalizeDisplayMathBlocks', () => {
  it('normalizes parenthesized and bracketed TeX delimiters', () => {
    expect(normalizeDisplayMathBlocks('角度是 \\(\\theta\\)')).toBe('角度是 $\\theta$');
    expect(normalizeDisplayMathBlocks('\\[x^2 + y^2 = z^2\\]')).toBe(
      '$$\nx^2 + y^2 = z^2\n$$',
    );
  });

  it('normalizes a standalone single-line display expression', () => {
    expect(normalizeDisplayMathBlocks('before\n$$x + y$$\nafter')).toBe(
      'before\n$$\nx + y\n$$\nafter',
    );
  });

  it('preserves TeX delimiters inside inline and fenced code', () => {
    const markdown = [
      'Use `\\(x\\)` as an example.',
      '```latex',
      '\\[x + y\\]',
      '```',
      'Render \\(z\\).',
    ].join('\n');

    expect(normalizeDisplayMathBlocks(markdown)).toBe([
      'Use `\\(x\\)` as an example.',
      '```latex',
      '\\[x + y\\]',
      '```',
      'Render $z$.',
    ].join('\n'));
  });

  it('preserves escaped literal delimiter commands', () => {
    expect(normalizeDisplayMathBlocks(String.raw`literal \\(x\\)`)).toBe(
      String.raw`literal \\(x\\)`,
    );
  });
});
