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

  it('preserves indentation when expanding display math inside Markdown lists', () => {
    const markdown = [
      '* 先把裡面的 $(2x + 1)$ 當成一個整體，只看最外面的 3 次方：',
      '  $$(\\text{整體})^3 \\xrightarrow{\\text{微分}} 3 \\times (\\text{整體})^2$$',
      '* 得到：**$3(2x + 1)^2$**',
    ].join('\n');

    expect(normalizeDisplayMathBlocks(markdown)).toBe([
      '* 先把裡面的 $(2x + 1)$ 當成一個整體，只看最外面的 3 次方：',
      '  $$',
      '  (\\text{整體})^3 \\xrightarrow{\\text{微分}} 3 \\times (\\text{整體})^2',
      '  $$',
      '* 得到：**$3(2x + 1)^2$**',
    ].join('\n'));
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
