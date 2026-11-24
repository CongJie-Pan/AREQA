/**
 * Avatar URLs come from user-editable profile metadata. Only web images are
 * rendered; anything else (e.g. `javascript:`) falls back to the initial.
 */
export function safeAvatarUrl(url?: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}
