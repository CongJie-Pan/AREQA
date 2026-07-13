interface HtmlNode {
  type?: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HtmlNode[];
}

/** Normalize a standalone single-line `$$...$$` block for remark-math. */
export function normalizeDisplayMathBlocks(content: string): string {
  return content.replace(
    /(^|\n)([ \t]*)\$\$([^\n]+?)\$\$([ \t]*)(?=\n|$)/g,
    (_match, prefix: string, indent: string, latex: string, trailing: string) =>
      `${prefix}${indent}$$\n${latex.trim()}\n${indent}$$${trailing}`,
  );
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
