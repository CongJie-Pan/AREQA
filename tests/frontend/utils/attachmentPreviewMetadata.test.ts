import { describe, expect, it } from 'vitest';
import {
  MAX_ATTACHMENT_PREVIEW_CHARS,
  filesToAttachmentMetadata,
  normalizeAttachmentMetadata,
  normalizeAttachmentPreview,
} from '@/utils/attachments';

const thumb = { dataUrl: 'data:image/jpeg;base64,/9j/4AAQSkZJRg==', width: 400, height: 300 };

describe('attachment preview metadata', () => {
  it('keeps a small inline raster thumbnail', () => {
    expect(normalizeAttachmentPreview(thumb)).toEqual(thumb);
  });

  it.each([
    ['remote url', { ...thumb, dataUrl: 'https://evil.example/x.jpg' }],
    ['svg payload', { ...thumb, dataUrl: 'data:image/svg+xml;base64,PHN2Zz4=' }],
    ['oversized', { ...thumb, dataUrl: `data:image/jpeg;base64,${'A'.repeat(MAX_ATTACHMENT_PREVIEW_CHARS)}` }],
    ['bad size', { ...thumb, width: 0 }],
    ['huge size', { ...thumb, height: 5000 }],
  ])('drops a %s thumbnail', (_label, value) => {
    expect(normalizeAttachmentPreview(value)).toBeUndefined();
  });

  it('attaches previews by index and survives cloud normalization', () => {
    const files = [new File(['x'], 'a.png', { type: 'image/png' }), new File(['y'], 'b.txt', { type: 'text/plain' })];
    const metadata = filesToAttachmentMetadata(files, [thumb, undefined]);

    expect(metadata[0].preview).toEqual(thumb);
    expect(metadata[1]).not.toHaveProperty('preview');
    expect(normalizeAttachmentMetadata(JSON.parse(JSON.stringify(metadata)))).toEqual(metadata);
  });
});
