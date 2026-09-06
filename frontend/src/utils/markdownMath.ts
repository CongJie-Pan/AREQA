interface HtmlNode {
  type?: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HtmlNode[];
}

/**
 * Normalize supported TeX delimiters without rewriting Markdown code spans.
 *
 * Args:
 *   content: Markdown source that may contain TeX math delimiters.
 *
 * Returns:
 *   Markdown with `\\(...\\)` converted to inline dollar delimiters,
 *   `\\[...\\]` converted to display dollar delimiters, and standalone
 *   single-line display math expanded for consistent streaming parsing.
 *
 * Compatibility:
 *   Fenced and inline code are preserved verbatim so documentation containing
 *   literal TeX examples is not interpreted as executable math markup.
 */
export function normalizeDisplayMathBlocks(content: string): string {
  const normalizedDelimiters = transformOutsideMarkdownCode(content, (segment) =>
    segment.replace(/\\([()[\]])/g, (match, delimiter: string, offset: number, source: string) => {
      let precedingSlashes = 0;
      for (let index = offset - 1; index >= 0 && source[index] === '\\'; index -= 1) {
        precedingSlashes += 1;
      }
      if (precedingSlashes % 2 === 1) return match;
      return delimiter === '(' || delimiter === ')' ? '$' : '$$';
    }),
  );

  return normalizedDelimiters.replace(
    /(^|\n)([ \t]*)\$\$([^\n]+?)\$\$([ \t]*)(?=\n|$)/g,
    (_match, prefix: string, indent: string, latex: string, trailing: string) =>
      `${prefix}${indent}$$\n${indent}${latex.trim()}\n${indent}$$${trailing}`,
  );
}

/**
 * Normalize loose bold markers emitted by models while preserving code text.
 *
 * Args:
 *   content: Markdown source that may contain strong-emphasis markers with
 *     padding spaces, such as `** important **`.
 *
 * Returns:
 *   Markdown with loose asterisk strong markers tightened to CommonMark-friendly
 *   form outside fenced and inline code.
 *
 * Compatibility:
 *   This intentionally handles only `**...**` strong markers because broad
 *   emphasis rewrites can change arithmetic, identifiers, and prose that happen
 *   to contain underscores or single asterisks.
 */
export function normalizeLooseStrongMarkers(content: string): string {
  return transformOutsideMarkdownCode(content, (segment) =>
    segment.replace(
      /(^|[^*])\*\*[ \t]+([^*\n][^\n]*?\S)[ \t]+\*\*(?!\*)/g,
      (_match, prefix: string, text: string) => `${prefix}**${text}**`,
    ),
  );
}

/** Transform plain Markdown segments while preserving inline and fenced code. */
function transformOutsideMarkdownCode(
  content: string,
  transform: (segment: string) => string,
): string {
  let fence: { marker: '`' | '~'; length: number } | null = null;

  return content
    .split(/(\n)/)
    .map((line) => {
      if (line === '\n') return line;

      const fenceMatch = line.match(/^[ \t]{0,3}(`{3,}|~{3,})/);
      if (fenceMatch) {
        const markerRun = fenceMatch[1];
        const marker = markerRun[0] as '`' | '~';
        if (!fence) {
          fence = { marker, length: markerRun.length };
        } else if (fence.marker === marker && markerRun.length >= fence.length) {
          fence = null;
        }
        return line;
      }

      if (fence) return line;
      return transformOutsideInlineCode(line, transform);
    })
    .join('');
}

/** Transform one Markdown line while preserving complete or partial code spans. */
function transformOutsideInlineCode(
  line: string,
  transform: (segment: string) => string,
): string {
  let result = '';
  let cursor = 0;

  while (cursor < line.length) {
    const openingIndex = line.indexOf('`', cursor);
    if (openingIndex === -1) return result + transform(line.slice(cursor));

    result += transform(line.slice(cursor, openingIndex));
    let openingEnd = openingIndex;
    while (line[openingEnd] === '`') openingEnd += 1;
    const delimiter = line.slice(openingIndex, openingEnd);
    const closingIndex = line.indexOf(delimiter, openingEnd);
    if (closingIndex === -1) return result + line.slice(openingIndex);

    const closingEnd = closingIndex + delimiter.length;
    result += line.slice(openingIndex, closingEnd);
    cursor = closingEnd;
  }

  return result;
}

/** Copy the original TeX annotation onto KaTeX display nodes for the UI. */
export function rehypeMathSource() {
  return (tree: HtmlNode) => {
    const findAnnotation = (node: HtmlNode): string | null => {
      if (node.tagName === 'annotation') {
        const collectText = (textNode: HtmlNode): string => {
          if (typeof textNode.value === 'string') return textNode.value;
          return (textNode.children || []).map(collectText).join('');
        };
        return collectText(node);
      }

      for (const child of node.children || []) {
        const value = findAnnotation(child);
        if (value !== null) return value;
      }

      return null;
    };

    const visit = (node: HtmlNode) => {
      const className = node.properties?.className;
      const classes = Array.isArray(className) ? className : [className];
      if (node.tagName === 'span' && classes.includes('katex-display')) {
        const latex = findAnnotation(node);
        if (latex !== null) {
          node.properties = { ...node.properties, 'data-latex': latex };
        }
      }
      node.children?.forEach(visit);
    };

    visit(tree);
  };
}
