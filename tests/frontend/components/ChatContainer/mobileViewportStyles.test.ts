import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

describe('ChatContainer mobile viewport styles', () => {
  it('anchors the chat shell at the layout viewport top while visualViewport height changes', () => {
    const globalsCss = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/app/globals.css'),
      'utf8',
    );
    const chatContainerStyles = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/ChatContainer/styles.ts'),
      'utf8',
    );

    expect(globalsCss).toMatch(/\.areqa-chat-shell\s*{[^}]*top:\s*0;/s);
    expect(chatContainerStyles).toMatch(/container:\s*css`[^`]*top:\s*0;/s);
    expect(chatContainerStyles).toContain('height: var(--areqa-visual-viewport-height, 100dvh);');
  });
});
