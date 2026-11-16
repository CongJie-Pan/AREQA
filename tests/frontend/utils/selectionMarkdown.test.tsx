import React from 'react';
import { render } from '@testing-library/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { afterEach, describe, expect, it } from 'vitest';
import { renderedMarkdownToMarkdown, selectionToMarkdown } from '@/utils/selectionMarkdown';

function renderMarkdown(markdown: string): HTMLElement {
  const { container } = render(
    <div data-role="assistant-bubble">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {markdown}
      </ReactMarkdown>
    </div>,
  );
  return container.firstElementChild as HTMLElement;
}

function selectNodeContents(node: Node): Selection {
  const selection = window.getSelection()!;
  const range = document.createRange();
  range.selectNodeContents(node);
  selection.removeAllRanges();
  selection.addRange(range);
  return selection;
}

afterEach(() => {
  window.getSelection()?.removeAllRanges();
});

describe('renderedMarkdownToMarkdown', () => {
  it('restores TeX delimiters for inline and display math', () => {
    const bubble = renderMarkdown('Energy is $E = mc^2$ here.\n\n$$\n\\int_0^1 x^2\\,dx = \\frac{1}{3}\n$$');
    expect(renderedMarkdownToMarkdown(bubble)).toBe(
      'Energy is $E = mc^2$ here.\n\n$$\n\\int_0^1 x^2\\,dx = \\frac{1}{3}\n$$',
    );
  });

  it('keeps headings, emphasis, lists, quotes, links, and code', () => {
    const source = [
      '## Steps',
      '',
      'Use **bold**, *italic*, `inline` and [docs](https://example.com).',
      '',
      '1. First $a+b$',
      '2. Second',
      '   - nested',
      '',
      '> quoted line',
      '',
      '```python',
      'def f(x):',
      '',
      '',
      '    return x',
      '```',
    ].join('\n');
    expect(renderedMarkdownToMarkdown(renderMarkdown(source))).toBe(source);
  });

  it('serializes GFM tables with math cells', () => {
    const source = '| x | f(x) |\n| --- | --- |\n| 1 | $x^2$ |';
    expect(renderedMarkdownToMarkdown(renderMarkdown(source))).toBe(source);
  });

  it('skips UI controls rendered inside the reply', () => {
    const root = document.createElement('div');
    root.innerHTML = '<p>Text<button>Copy formula</button></p><div class="areqa-markdown-code-header">python</div>';
    expect(renderedMarkdownToMarkdown(root)).toBe('Text');
  });
});

describe('selectionToMarkdown', () => {
  it('expands a selection that starts inside a formula to the whole formula', () => {
    const bubble = renderMarkdown('Let $x^2 + 1$ be positive.');
    const glyph = bubble.querySelector('.katex-html')!;
    const textNode = bubble.querySelector('p')!.lastChild!;
    const selection = window.getSelection()!;
    const range = document.createRange();
    range.setStart(glyph.firstChild!, 0);
    range.setEnd(textNode, textNode.textContent!.length);
    selection.removeAllRanges();
    selection.addRange(range);

    expect(selectionToMarkdown(selection, bubble)).toBe('$x^2 + 1$ be positive.');
  });

  it('returns code text verbatim when the selection is inside a code block', () => {
    const bubble = renderMarkdown('```js\nconst a = 1;\n\nconst b = 2;\n```');
    const selection = selectNodeContents(bubble.querySelector('code')!);
    expect(selectionToMarkdown(selection, bubble)).toBe('const a = 1;\n\nconst b = 2;\n');
  });

  it('returns null outside the container or for an empty selection', () => {
    const bubble = renderMarkdown('Inside');
    const outside = document.createElement('p');
    outside.textContent = 'Outside';
    document.body.appendChild(outside);

    expect(selectionToMarkdown(selectNodeContents(outside), bubble)).toBeNull();
    window.getSelection()!.removeAllRanges();
    expect(selectionToMarkdown(window.getSelection(), bubble)).toBeNull();
    outside.remove();
  });
});
