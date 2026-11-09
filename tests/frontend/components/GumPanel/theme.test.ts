import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const styles = readFileSync(path.resolve(__dirname, '../../../../frontend/src/components/GumPanel/styles.ts'), 'utf8');
const component = readFileSync(path.resolve(__dirname, '../../../../frontend/src/components/GumPanel/index.tsx'), 'utf8');

describe('Memory page theme surfaces', () => {
  it.each(['panel', 'heroSection', 'assetCard', 'suggestionCard'])('%s uses the active theme for its surface', rule => {
    const body = styles.match(new RegExp(`${rule}:\\s*css\x60([^\x60]*)\x60`))?.[1];
    expect(body).toBeDefined();
    expect(body).toMatch(/background:\s*(?:var\(--|linear-gradient\([^;]*var\(--)/);
    expect(body).not.toMatch(/background:\s*(?:#[\da-f]+|rgba\(30, 24, 38)/i);
  });

  it('uses theme-aware text and borders throughout the summary, assets and timeline', () => {
    expect(styles).not.toMatch(/(?:color|border(?:-bottom)?):[^;\n]*(?:#(?:fff\b|ffffff|aaa\b)|rgba\(255,\s*255,\s*255)/i);
    expect(component).not.toMatch(/color:\s*['"](?:#[\da-f]+|rgba\(255,\s*255,\s*255)/i);
  });
});
