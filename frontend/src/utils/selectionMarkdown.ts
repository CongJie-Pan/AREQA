/**
 * Turn a selection inside a rendered assistant reply back into Markdown.
 *
 * Browsers copy rendered Markdown as plain text, which flattens headings and
 * lists and turns KaTeX into a jumble of MathML and visual glyph text. These
 * helpers serialize the selected DOM instead, recovering TeX from KaTeX's
 * `application/x-tex` annotation so formulas paste back as `$...$` / `$$...$$`.
 */

const SKIPPED_SELECTOR = [
  'button',
  'script',
  'style',
  'input:not([type="checkbox"])',
  '[data-copy-ignore]',
  '.areqa-markdown-code-header',
  '.areqa-markdown-table-actions',
].join(',');

// Whole formulas are the smallest unit we copy: a partial KaTeX selection has
// no TeX annotation left to recover.
const MATH_SELECTOR = '.katex-display, .katex';

const PRESERVED_PLACEHOLDER = (index: number) => `\u0000${index}\u0000`;

interface SerializeContext {
  /** Verbatim blocks (code, display math) kept out of whitespace normalization. */
  preserved: string[];
}

function mathSource(element: Element): string {
  const annotation = element.querySelector('annotation[encoding="application/x-tex"]');
  return (element.getAttribute('data-latex') ?? annotation?.textContent ?? element.textContent ?? '').trim();
}

function preserve(context: SerializeContext, value: string): string {
  context.preserved.push(value);
  return PRESERVED_PLACEHOLDER(context.preserved.length - 1);
}

function block(content: string): string {
  return content.trim() ? `\n\n${content.trim()}\n\n` : '';
}

function normalizeBlocks(markdown: string): string {
  return markdown
    .split('\n')
    .map((line) => line.replace(/[ \t]+$/, ''))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function serializeChildren(node: Node, context: SerializeContext): string {
  return Array.from(node.childNodes).map((child) => serializeNode(child, context)).join('');
}

function serializeInline(node: Node, context: SerializeContext): string {
  return normalizeBlocks(serializeChildren(node, context)).replace(/\s*\n\s*/g, ' ');
}

function wrapInline(marker: string, content: string): string {
  const trimmed = content.trim();
  if (!trimmed) return content;
  const leading = content.match(/^\s*/)?.[0] ?? '';
  const trailing = content.match(/\s*$/)?.[0] ?? '';
  return `${leading}${marker}${trimmed}${marker}${trailing}`;
}

function inlineCode(text: string): string {
  const longestRun = Math.max(0, ...(text.match(/`+/g) ?? []).map((run) => run.length));
  const fence = '`'.repeat(longestRun + 1);
  const padding = text.startsWith('`') || text.endsWith('`') ? ' ' : '';
  return `${fence}${padding}${text}${padding}${fence}`;
}

function codeBlock(pre: Element): string {
  const code = pre.querySelector('code');
  const language = code?.className.match(/(?:^|\s)language-([^\s]+)/)?.[1] ?? '';
  const text = (pre.textContent ?? '').replace(/\n$/, '');
  const longestRun = Math.max(2, ...(text.match(/`+/g) ?? []).map((run) => run.length));
  const fence = '`'.repeat(longestRun + 1);
  return `${fence}${language}\n${text}\n${fence}`;
}

function indentContinuation(text: string, indent: string): string {
  return text
    .split('\n')
    .map((line, index) => (index === 0 || !line ? line : `${indent}${line}`))
    .join('\n');
}

function serializeList(list: Element, context: SerializeContext): string {
  const ordered = list.tagName === 'OL';
  const start = Number.parseInt(list.getAttribute('start') ?? '1', 10) || 1;
  const items = Array.from(list.children).filter((child) => child.tagName === 'LI');
  const lines = items.map((item, index) => {
    const marker = ordered ? `${start + index}. ` : '- ';
    // Nested lists attach on the next line; a blank line would make the list loose.
    const content = normalizeBlocks(
      Array.from(item.childNodes)
        .map((child) =>
          child instanceof Element && (child.tagName === 'UL' || child.tagName === 'OL')
            ? `\n${serializeList(child, context).trim()}\n`
            : serializeNode(child, context),
        )
        .join(''),
    );
    return `${marker}${indentContinuation(content, ' '.repeat(marker.length))}`;
  });
  return block(lines.join('\n'));
}

function tableCell(cell: Element, context: SerializeContext): string {
  return serializeInline(cell, context).replace(/\|/g, '\\|');
}

function serializeTable(table: Element, context: SerializeContext): string {
  const rows = Array.from(table.querySelectorAll('tr'));
  if (rows.length === 0) return '';
  const cells = rows.map((row) => Array.from(row.children).map((cell) => tableCell(cell, context)));
  const width = Math.max(...cells.map((row) => row.length));
  const line = (row: string[]) => `| ${Array.from({ length: width }, (_, i) => row[i] ?? '').join(' | ')} |`;
  const separator = `| ${Array.from({ length: width }, () => '---').join(' | ')} |`;
  return block([line(cells[0]), separator, ...cells.slice(1).map(line)].join('\n'));
}

function serializeElement(element: Element, context: SerializeContext): string {
  if (element.matches(SKIPPED_SELECTOR)) return '';

  if (element.matches('.katex-display')) {
    return block(preserve(context, `$$\n${mathSource(element)}\n$$`));
  }
  if (element.matches('.katex')) {
    return `$${mathSource(element)}$`;
  }

  const tag = element.tagName;
  switch (tag) {
    case 'H1':
    case 'H2':
    case 'H3':
    case 'H4':
    case 'H5':
    case 'H6':
      return block(`${'#'.repeat(Number(tag[1]))} ${serializeInline(element, context)}`);
    case 'P':
      return block(serializeChildren(element, context));
    case 'BR':
      return '\n';
    case 'HR':
      return block('---');
    case 'STRONG':
    case 'B':
      return wrapInline('**', serializeChildren(element, context));
    case 'EM':
    case 'I':
      return wrapInline('*', serializeChildren(element, context));
    case 'DEL':
    case 'S':
      return wrapInline('~~', serializeChildren(element, context));
    case 'CODE':
      return inlineCode(element.textContent ?? '');
    case 'PRE':
      return block(preserve(context, codeBlock(element)));
    case 'A': {
      const text = serializeChildren(element, context).trim();
      const href = element.getAttribute('href');
      return href && text && text !== href ? `[${text}](${href})` : text || href || '';
    }
    case 'IMG': {
      const alt = element.getAttribute('alt') ?? '';
      const src = element.getAttribute('src') ?? '';
      // Inline data URLs would flood the clipboard; keep only the description.
      return src && !src.startsWith('data:') ? `![${alt}](${src})` : alt;
    }
    case 'INPUT':
      return (element as HTMLInputElement).checked ? '[x] ' : '[ ] ';
    case 'UL':
    case 'OL':
      return serializeList(element, context);
    case 'LI':
      // A bare item appears when the selection starts or ends inside a list.
      return block(`- ${normalizeBlocks(serializeChildren(element, context))}`);
    case 'BLOCKQUOTE': {
      const content = normalizeBlocks(serializeChildren(element, context));
      return block(content.split('\n').map((line) => (line ? `> ${line}` : '>')).join('\n'));
    }
    case 'TABLE':
      return serializeTable(element, context);
    case 'TR':
      return `\n| ${Array.from(element.children).map((cell) => tableCell(cell, context)).join(' | ')} |\n`;
    case 'DIV':
    case 'SECTION':
    case 'FIGURE':
    case 'FIGCAPTION':
      return block(serializeChildren(element, context));
    default:
      return serializeChildren(element, context);
  }
}

function serializeNode(node: Node, context: SerializeContext): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return (node.textContent ?? '').replace(/[ \t\r\n]+/g, ' ');
  }
  if (node.nodeType === Node.ELEMENT_NODE) {
    return serializeElement(node as Element, context);
  }
  if (node.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
    return serializeChildren(node, context);
  }
  return '';
}

/**
 * Serialize rendered Markdown DOM (an element or a cloned range fragment).
 *
 * Args:
 *   root: Rendered reply content, typically `Range.cloneContents()`.
 *
 * Returns:
 *   Markdown text with KaTeX restored to TeX delimiters.
 */
export function renderedMarkdownToMarkdown(root: Node): string {
  const context: SerializeContext = { preserved: [] };
  const markdown = normalizeBlocks(serializeNode(root, context));
  return markdown.replace(/\u0000(\d+)\u0000/g, (_match, index: string) => context.preserved[Number(index)] ?? '');
}

function closestElement(node: Node, selector: string): Element | null {
  const element = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
  return element?.closest(selector) ?? null;
}

/**
 * Convert the current selection to Markdown when it lies inside `container`.
 *
 * Args:
 *   selection: The document selection.
 *   container: Optional bound; both selection ends must be inside it.
 *
 * Returns:
 *   Markdown for the selection, or null when there is nothing to convert so
 *   callers keep the browser's default copy behavior.
 */
export function selectionToMarkdown(selection: Selection | null, container?: Element | null): string | null {
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const original = selection.getRangeAt(0);
  if (container && !(container.contains(original.startContainer) && container.contains(original.endContainer))) {
    return null;
  }

  // Inside a code block the visible text already is the source.
  if (closestElement(original.commonAncestorContainer, 'pre')) {
    return original.toString() || null;
  }

  const range = original.cloneRange();
  const startMath = closestElement(range.startContainer, MATH_SELECTOR);
  const endMath = closestElement(range.endContainer, MATH_SELECTOR);
  if (startMath) range.setStartBefore(startMath.closest('.katex-display') ?? startMath);
  if (endMath) range.setEndAfter(endMath.closest('.katex-display') ?? endMath);

  const markdown = renderedMarkdownToMarkdown(range.cloneContents());
  return markdown || null;
}
