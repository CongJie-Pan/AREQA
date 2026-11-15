/**
 * Browser-side attachment thumbnails.
 *
 * A small JPEG thumbnail (an image, or a PDF's first page) is the only
 * file-derived data persisted with a message; original bytes stay in memory
 * for the current session (see `attachmentSession.ts`). Every step fails soft:
 * a file without a thumbnail falls back to the plain attachment card.
 */
import type { AttachmentPreview } from '@/database/schema';
import { MAX_ATTACHMENT_PREVIEW_CHARS } from '@/utils/attachments';

/** Longest thumbnail edge in pixels: sharp at the 240 px display size. */
export const ATTACHMENT_PREVIEW_EDGE = 400;
const JPEG_QUALITIES = [0.82, 0.7, 0.55, 0.4];
const PDF_MEDIA_TYPE = 'application/pdf';

const previewCache = new WeakMap<File, Promise<AttachmentPreview | undefined>>();

export function isPdfFile(file: Pick<File, 'type' | 'name'>): boolean {
  return file.type === PDF_MEDIA_TYPE || (!file.type && file.name.toLowerCase().endsWith('.pdf'));
}

function fitSize(width: number, height: number, edge: number): { width: number; height: number } {
  const scale = Math.min(1, edge / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

function encodeCanvas(canvas: HTMLCanvasElement, maxChars: number): string | undefined {
  for (const quality of JPEG_QUALITIES) {
    const dataUrl = canvas.toDataURL('image/jpeg', quality);
    if (dataUrl.startsWith('data:image/jpeg') && dataUrl.length <= maxChars) return dataUrl;
  }
  return undefined;
}

function whiteCanvas(width: number, height: number): { canvas: HTMLCanvasElement; context: CanvasRenderingContext2D } | undefined {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) return undefined;
  // JPEG has no alpha; transparent PNGs and PDF pages render on white.
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, width, height);
  return { canvas, context };
}

async function imagePreview(file: File, edge: number, maxChars: number): Promise<AttachmentPreview | undefined> {
  const bitmap = await createImageBitmap(file);
  try {
    const size = fitSize(bitmap.width, bitmap.height, edge);
    const surface = whiteCanvas(size.width, size.height);
    if (!surface) return undefined;
    surface.context.drawImage(bitmap, 0, 0, size.width, size.height);
    const dataUrl = encodeCanvas(surface.canvas, maxChars);
    return dataUrl ? { dataUrl, ...size } : undefined;
  } finally {
    bitmap.close();
  }
}

async function loadPdfjs() {
  const pdfjs = await import('pdfjs-dist');
  const scope = globalThis as typeof globalThis & { pdfjsWorker?: unknown };
  if (!scope.pdfjsWorker) {
    // Run the worker code on the main thread: one first-page render is cheap,
    // and it avoids bundler-specific worker URL handling.
    scope.pdfjsWorker = await import('pdfjs-dist/build/pdf.worker.min.mjs');
  }
  return pdfjs;
}

/**
 * Render a PDF's first page to a JPEG data URL.
 *
 * Args:
 *   file: PDF file held in memory.
 *   edge: Longest output edge in pixels.
 *   maxChars: Upper bound for the encoded data URL.
 */
export async function renderPdfFirstPage(
  file: File,
  edge: number = ATTACHMENT_PREVIEW_EDGE,
  maxChars: number = MAX_ATTACHMENT_PREVIEW_CHARS,
): Promise<AttachmentPreview | undefined> {
  const pdfjs = await loadPdfjs();
  const loadingTask = pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) });
  try {
    const document = await loadingTask.promise;
    const page = await document.getPage(1);
    const base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: edge / Math.max(base.width, base.height) });
    const size = { width: Math.round(viewport.width), height: Math.round(viewport.height) };
    const surface = whiteCanvas(size.width, size.height);
    if (!surface) return undefined;
    await page.render({ canvas: surface.canvas, canvasContext: surface.context, viewport }).promise;
    page.cleanup();
    const dataUrl = encodeCanvas(surface.canvas, maxChars);
    return dataUrl ? { dataUrl, ...size } : undefined;
  } finally {
    await loadingTask.destroy();
  }
}

async function buildPreview(file: File): Promise<AttachmentPreview | undefined> {
  try {
    if (file.type.startsWith('image/')) {
      return await imagePreview(file, ATTACHMENT_PREVIEW_EDGE, MAX_ATTACHMENT_PREVIEW_CHARS);
    }
    if (isPdfFile(file)) return await renderPdfFirstPage(file);
  } catch {
    // Corrupt, encrypted or unsupported files keep the plain attachment card.
  }
  return undefined;
}

/**
 * Start (or reuse) thumbnail generation for a file. Call this when the file is
 * attached so the work overlaps with the learner typing.
 */
export function prefetchAttachmentPreview(file: File): Promise<AttachmentPreview | undefined> {
  let pending = previewCache.get(file);
  if (!pending) {
    pending = buildPreview(file);
    previewCache.set(file, pending);
  }
  return pending;
}

/**
 * Collect thumbnails for a send, waiting at most `timeoutMs` so a slow PDF
 * never delays the message; late thumbnails are simply omitted.
 */
export async function collectAttachmentPreviews(
  files: File[],
  timeoutMs = 1500,
): Promise<Array<AttachmentPreview | undefined>> {
  if (files.length === 0) return [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<undefined>((resolve) => {
    timer = setTimeout(() => resolve(undefined), timeoutMs);
  });
  try {
    return await Promise.all(files.map((file) => Promise.race([prefetchAttachmentPreview(file), deadline])));
  } finally {
    if (timer) clearTimeout(timer);
  }
}
