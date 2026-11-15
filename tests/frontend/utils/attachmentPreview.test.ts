import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('pdfjs-dist', () => ({
  // A PDF that never finishes loading must not hold the send.
  getDocument: vi.fn(() => ({ promise: new Promise(() => undefined), destroy: vi.fn() })),
}));
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs', () => ({ WorkerMessageHandler: {} }));

import { collectAttachmentPreviews, prefetchAttachmentPreview } from '@/utils/attachmentPreview';

describe('attachment preview generation', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('gives up on a slow PDF after the send budget', async () => {
    vi.useFakeTimers();
    const pdf = new File(['%PDF-1.4'], 'slow.pdf', { type: 'application/pdf' });
    const pending = collectAttachmentPreviews([pdf], 1500);
    await vi.advanceTimersByTimeAsync(1500);
    await expect(pending).resolves.toEqual([undefined]);
  });

  it('fails soft when the browser cannot decode an image', async () => {
    const image = new File(['not an image'], 'broken.png', { type: 'image/png' });
    await expect(prefetchAttachmentPreview(image)).resolves.toBeUndefined();
  });

  it('reuses one generation per file', () => {
    const file = new File(['x'], 'notes.txt', { type: 'text/plain' });
    expect(prefetchAttachmentPreview(file)).toBe(prefetchAttachmentPreview(file));
  });
});
