import type { AttachmentMetadata, AttachmentPreview } from '@/database/schema';

const LEGACY_ATTACHMENT_MARKER = /(?:\r?\n)*\[已附加\s+(\d+)\s+個檔案\]\s*$/;
const MAX_DISPLAY_FILENAME_LENGTH = 120;

function sanitizeAttachmentName(name: string): string {
  const basename = name.replace(/\\/g, '/').split('/').pop() ?? '';
  const sanitized = basename
    .replace(/[\u0000-\u001f\u007f]/g, '_')
    .trim()
    .slice(0, MAX_DISPLAY_FILENAME_LENGTH);
  return sanitized || '附件';
}

/** Upper bound for a persisted thumbnail data URL (~45 KB of JPEG). */
export const MAX_ATTACHMENT_PREVIEW_CHARS = 60_000;
const MAX_PREVIEW_EDGE = 640;
const PREVIEW_DATA_URL = /^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/;

/**
 * Accept only small inline raster thumbnails; anything else is dropped so
 * synced metadata can never smuggle remote URLs or oversized payloads.
 */
export function normalizeAttachmentPreview(value: unknown): AttachmentPreview | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const candidate = value as Record<string, unknown>;
  const { dataUrl, width, height } = candidate;
  if (
    typeof dataUrl !== 'string'
    || dataUrl.length > MAX_ATTACHMENT_PREVIEW_CHARS
    || !PREVIEW_DATA_URL.test(dataUrl)
    || typeof width !== 'number' || typeof height !== 'number'
    || !Number.isFinite(width) || !Number.isFinite(height)
    || width < 1 || height < 1 || width > MAX_PREVIEW_EDGE || height > MAX_PREVIEW_EDGE
  ) {
    return undefined;
  }
  return { dataUrl, width: Math.round(width), height: Math.round(height) };
}

export function filesToAttachmentMetadata(
  files: File[],
  previews: ReadonlyArray<AttachmentPreview | undefined> = [],
): AttachmentMetadata[] {
  return files.map((file, index) => {
    const preview = normalizeAttachmentPreview(previews[index]);
    return {
      name: sanitizeAttachmentName(file.name),
      mediaType: file.type || 'application/octet-stream',
      sizeBytes: file.size,
      ...(preview ? { preview } : {}),
    };
  });
}

export function normalizeAttachmentMetadata(value: unknown): AttachmentMetadata[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const candidate = item as Record<string, unknown>;
    if (
      typeof candidate.name !== 'string' ||
      typeof candidate.mediaType !== 'string' ||
      typeof candidate.sizeBytes !== 'number' ||
      !Number.isFinite(candidate.sizeBytes) ||
      candidate.sizeBytes < 0
    ) {
      return [];
    }
    const preview = normalizeAttachmentPreview(candidate.preview);
    return [{
      name: sanitizeAttachmentName(candidate.name),
      mediaType: candidate.mediaType.slice(0, 100),
      sizeBytes: candidate.sizeBytes,
      ...(preview ? { preview } : {}),
    }];
  });
}

export function splitLegacyAttachmentMarker(content: string): {
  content: string;
  legacyCount: number;
} {
  const match = content.match(LEGACY_ATTACHMENT_MARKER);
  if (!match) return { content, legacyCount: 0 };

  const count = Number.parseInt(match[1], 10);
  return {
    content: content.replace(LEGACY_ATTACHMENT_MARKER, '').trimEnd(),
    legacyCount: Number.isFinite(count) && count > 0 ? Math.min(count, 5) : 0,
  };
}

export function createLegacyAttachmentMetadata(count: number): AttachmentMetadata[] {
  return Array.from({ length: count }, (_, index) => ({
    name: `附件 ${index + 1}`,
    mediaType: 'application/octet-stream',
    sizeBytes: 0,
  }));
}
