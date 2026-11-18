import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const globals = readFileSync(path.resolve(__dirname, '../../../frontend/src/app/globals.css'), 'utf8');
const rule = (selector: string) => globals.match(new RegExp(`\\n${selector.replace('.', '\\.')}\\s*{([^}]*)}`))?.[1] ?? '';

describe('empty-home workspace switch layout', () => {
  it('anchors to the chat column from the first stylesheet, before CSS-in-JS loads', () => {
    // Without this, the switch first centres on the whole viewport and then jumps.
    expect(rule('.areqa-chat-main')).toMatch(/position:\s*relative;/);
  });

  it('is centred near the top of that column', () => {
    const slot = rule('.areqa-workspace-switch-home-slot');
    expect(slot).toMatch(/position:\s*absolute;/);
    expect(slot).toMatch(/left:\s*50%;/);
    expect(slot).toMatch(/transform:\s*translateX\(-50%\);/);
    expect(slot).toMatch(/top:\s*max\(16px, env\(safe-area-inset-top\)\);/);
  });
});
