import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const source = (file: string) => readFileSync(
  path.resolve(__dirname, '../../../frontend/src', file), 'utf8',
);

describe('chat surfaces follow the interface theme', () => {
  it('switches the input surface to white in light mode for both initial paint and hydrated styles', () => {
    const globals = source('app/globals.css');
    const lightTheme = globals.match(/html\[data-interface-theme='light'\]\s*{([^}]*)}/)?.[1];
    expect(lightTheme).toContain('--areqa-chat-input-background: #ffffff;');
    expect(globals).toMatch(/\.areqa-chat-input-shell\s*{[^}]*background:\s*var\(--areqa-chat-input-background\);/);
    expect(source('components/ChatInput/index.tsx')).toContain("'areqa-chat-input-shell'");
  });

  it.each([
    ['ChatInput/styles.ts', 'imageAttachmentRemove'],
    ['MessageList/styles.ts', 'messageAttachmentCard'],
    ['MessageList/styles.ts', 'messageAttachmentToggle'],
    ['MessageList/styles.ts', 'messageAttachmentDropdown'],
    ['Citations/styles.ts', 'sourceCard'],
  ])('%s %s uses theme colors for its surface', (file, rule) => {
    const css = source(`components/${file}`).match(new RegExp(`${rule}:\\s*css\x60([^\x60]*)\x60`))?.[1];
    expect(css).toBeDefined();
    expect(css).toMatch(/background:\s*(?:var\(--|color-mix\(in srgb, var\(--)/);
    expect(css).not.toMatch(/(?:background|color|border-color):\s*(?:#[0-9a-f]+|rgba\(255, 255, 255)/i);
  });

  it('keeps citation markdown and modal inline styles free of fixed dark surfaces and white text', () => {
    const styles = source('components/Citations/styles.ts');
    const component = source('components/Citations/index.tsx');
    expect(styles).not.toMatch(/(?:background|color):\s*(?:#[0-9a-f]+|rgba\(255, 255, 255)/i);
    expect(component).not.toMatch(/(?:background|color|borderColor):\s*['"](?:#(?:262626|333333|ffffff|f0f0f0|bfbfbf)|rgba\(255, 255, 255)/i);
  });
});
