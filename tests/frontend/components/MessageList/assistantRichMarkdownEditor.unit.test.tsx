import { describe, expect, it } from 'vitest';
import {
  editorHtmlToMarkdown,
  inlineMarkdownToEditorHtml,
  markdownToEditorHtml,
  parseMarkdownTableRow,
} from '../../../../frontend/src/components/MessageList/MessageItem';

function roundTrip(markdown: string): string {
  const root = document.createElement('div');
  root.innerHTML = markdownToEditorHtml(markdown);
  return editorHtmlToMarkdown(root);
}

describe('assistant rich markdown editor conversion utilities', () => {
  it('parses escaped table pipes as one cell', () => {
    expect(parseMarkdownTableRow('| A\\|B | C |')).toEqual(['A|B', 'C']);
  });

  it('keeps URLs, blockquote inline formatting, blank table rows, and fenced code stable', () => {
    const markdown = [
      '| A\\|B | C |',
      '| --- | --- |',
      '| 1 | 2 |',
      '|  |  |',
      '',
      '> **important** [link](https://example.com/?a=1&b=2)',
      '',
      '```js',
      'const foo_bar_baz = 1;',
      '```',
    ].join('\n');

    expect(roundTrip(markdown)).toBe(markdown);
  });

  it('renders inline markdown without turning underscores inside code into emphasis', () => {
    const html = inlineMarkdownToEditorHtml('`foo_bar_baz` [link](https://example.com/?a=1&b=2)');

    expect(html).toContain('<code>foo_bar_baz</code>');
    expect(html).not.toContain('<em>');
    expect(html).toContain('href="https://example.com/?a=1&amp;b=2"');
  });

  it('serializes root text nodes instead of dropping edited text', () => {
    const root = document.createElement('div');
    root.append('replacement text');

    expect(editorHtmlToMarkdown(root)).toBe('replacement text');
  });

  it('preserves markdown blocks when the browser wraps editor content', () => {
    const root = document.createElement('div');
    root.innerHTML = [
      '<div><ul><li data-depth="0">test</li></ul></div>',
      '<div><ol><li data-depth="0">first</li></ol></div>',
      '<section><blockquote><strong>note</strong></blockquote></section>',
    ].join('');

    expect(editorHtmlToMarkdown(root)).toBe([
      '- test',
      '',
      '1. first',
      '',
      '> **note**',
    ].join('\n'));
  });
});
