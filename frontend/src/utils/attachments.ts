import type { AttachmentMetadata } from '@/database/schema';

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

export function filesToAttachmentMetadata(files: File[]): AttachmentMetadata[] {
  return files.map((file) => ({
    name: sanitizeAttachmentName(file.name),
    mediaType: file.type || 'application/octet-stream',
    sizeBytes: file.size,
  }));
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
    return [{
      name: sanitizeAttachmentName(candidate.name),
      mediaType: candidate.mediaType.slice(0, 100),
      sizeBytes: candidate.sizeBytes,
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
