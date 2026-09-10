import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

describe('NotesPanel styles', () => {
  it('keeps saved note cards compact without forcing bold latin text', () => {
    const styles = readFileSync(
      path.resolve(__dirname, '../../../../frontend/src/components/NotesPanel/styles.ts'),
      'utf8',
    );
    const noteCardRule = styles.match(/noteCard:\s*css`(?<body>[^`]*)`/s);
    const noteBodyRule = styles.match(/noteBody:\s*css`(?<body>[^`]*)`/s);
    const latinTextRule = styles.match(/latinText:\s*css`(?<body>[^`]*)`/s);

    expect(noteCardRule?.groups?.body ?? '').toContain('gap: 8px;');
    expect(noteCardRule?.groups?.body ?? '').toContain('padding: 12px 14px;');
    expect(noteBodyRule?.groups?.body ?? '').toContain('line-height: 1.6;');
    expect(latinTextRule?.groups?.body ?? '').toContain('font-family: "Times New Roman", Times, serif;');
    expect(latinTextRule?.groups?.body ?? '').not.toContain('font-weight');
  });
});
