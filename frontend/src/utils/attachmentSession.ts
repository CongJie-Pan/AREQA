/**
 * Session-only registry of original attachment files.
 *
 * Originals are never persisted (only thumbnails are). While the tab stays
 * open, the message that uploaded a file can still show it full size and offer
 * a download; after a reload these lookups return undefined and the UI falls
 * back to the stored thumbnail.
 */
const originals = new Map<string, File[]>();
// One object URL per original; the file is already held for the session, so
// the URL adds no copy and stays valid across React StrictMode remounts.
const objectUrls = new Map<File, string>();

export function rememberSessionAttachments(messageId: string, files: File[]): void {
  if (messageId && files.length > 0) originals.set(messageId, [...files]);
}

export function getSessionAttachment(messageId: string, index: number): File | undefined {
  return originals.get(messageId)?.[index];
}

export function getSessionAttachmentUrl(file: File): string {
  let url = objectUrls.get(file);
  if (!url) {
    url = URL.createObjectURL(file);
    objectUrls.set(file, url);
  }
  return url;
}

/** Test helper and logout hook: drop every in-memory original. */
export function clearSessionAttachments(): void {
  objectUrls.forEach((url) => URL.revokeObjectURL(url));
  objectUrls.clear();
  originals.clear();
}
