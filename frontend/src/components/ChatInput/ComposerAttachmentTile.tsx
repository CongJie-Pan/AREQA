'use client';

/**
 * One pending attachment in the composer, drawn as a uniform square tile:
 * images show the picture, PDFs their first page (from the thumbnail made at
 * attach time), and other files their name, line count and type badge.
 */
import React, { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { createStyles } from 'antd-style';
import type { AttachmentPreview } from '@/database/schema';
import { isPdfFile, prefetchAttachmentPreview } from '@/utils/attachmentPreview';

const TEXT_LINE_COUNT_MAX_BYTES = 2 * 1024 * 1024;
const TEXT_EXTENSIONS = new Set(['txt', 'md', 'markdown', 'csv', 'json', 'tsv', 'log']);
/** Images narrower than this are flagged like Claude's "Low res" badge. */
const LOW_RES_EDGE = 300;

const useStyles = createStyles(({ css }) => ({
  tile: css`
    position: relative;
    flex: 0 0 auto;
    width: 112px;
    height: 112px;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--foreground) 12%, transparent);
    border-radius: 12px;
    background: color-mix(in srgb, var(--foreground) 5%, var(--areqa-chat-input-background));

    @media (max-width: 768px) {
      width: 88px;
      height: 88px;
      border-radius: 10px;
    }

    &:hover .composer-tile-remove,
    &:focus-within .composer-tile-remove {
      opacity: 1;
    }
  `,
  cover: css`
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top center;
  `,
  textBody: css`
    display: flex;
    height: 100%;
    flex-direction: column;
    padding: 10px 10px 8px;
    box-sizing: border-box;
  `,
  name: css`
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    color: var(--foreground);
    font-size: 13px;
    font-weight: 600;
    line-height: 1.3;
    word-break: break-word;

    @media (max-width: 768px) {
      -webkit-line-clamp: 2;
      font-size: 12px;
    }
  `,
  meta: css`
    margin-top: 2px;
    color: color-mix(in srgb, var(--foreground) 55%, transparent);
    font-size: 11px;
  `,
  badge: css`
    position: absolute;
    left: 8px;
    bottom: 8px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 7px;
    border-radius: 6px;
    background: rgba(25, 25, 25, 0.78);
    color: #e8e8e8;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.03em;
    line-height: 18px;
  `,
  warn: css`
    color: #f0b35a;
  `,
  remove: css`
    position: absolute;
    top: 6px;
    right: 6px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    padding: 0;
    border: 0;
    border-radius: 999px;
    background: rgba(20, 20, 20, 0.82);
    color: #ffffff;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s ease;

    /* Touch screens have no hover: keep the control visible. */
    @media (hover: none) {
      opacity: 1;
    }

    &:focus-visible {
      opacity: 1;
      outline: 2px solid #d8a25c;
    }
  `,
}));

function extensionOf(name: string): string {
  const match = /\.([A-Za-z0-9]{1,8})$/.exec(name);
  return match ? match[1].toLowerCase() : '';
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Resolve a promise-based value for one file without blocking render. */
function useFileValue<T>(file: File, load: ((file: File) => Promise<T | undefined>) | null): T | undefined {
  const [state, setState] = useState<{ file: File; value: T | undefined } | null>(null);
  useEffect(() => {
    if (!load) return undefined;
    let active = true;
    load(file).then((value) => { if (active) setState({ file, value }); }).catch(() => undefined);
    return () => { active = false; };
  }, [file, load]);
  return state?.file === file ? state.value : undefined;
}

const loadPdfThumb = (file: File): Promise<AttachmentPreview | undefined> => prefetchAttachmentPreview(file);
/** Blob.text() is missing in older Safari; FileReader works everywhere. */
function readText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

const loadLineCount = async (file: File): Promise<number | undefined> => {
  if (file.size > TEXT_LINE_COUNT_MAX_BYTES) return undefined;
  const text = await readText(file);
  return text.length === 0 ? 0 : text.split(/\r\n|\r|\n/).length;
};

export function ComposerAttachmentTile({
  file, objectUrl, removeLabel, imageAlt, lineCountLabel, lowResLabel, onRemove,
}: {
  file: File;
  objectUrl: string | null;
  removeLabel: string;
  imageAlt: string;
  lineCountLabel: (count: number) => string;
  lowResLabel: string;
  onRemove: () => void;
}) {
  const { styles, cx } = useStyles();
  const isImage = Boolean(objectUrl && file.type.startsWith('image/'));
  const isPdf = isPdfFile(file);
  const extension = extensionOf(file.name);
  const isText = !isImage && !isPdf && (file.type.startsWith('text/') || TEXT_EXTENSIONS.has(extension));
  const pdfThumb = useFileValue(file, isPdf ? loadPdfThumb : null);
  const lineCount = useFileValue(file, isText ? loadLineCount : null);
  const [naturalWidth, setNaturalWidth] = useState(0);
  const badge = (isPdf ? 'pdf' : extension || 'file').toUpperCase();

  return (
    <div className={cx('areqa-chat-input-attachment-tile', styles.tile)} title={file.name}>
      {isImage ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={objectUrl ?? ''}
            alt={imageAlt}
            className={styles.cover}
            onLoad={(event) => setNaturalWidth(event.currentTarget.naturalWidth)}
          />
          {naturalWidth > 0 && naturalWidth < LOW_RES_EDGE && (
            <span className={cx(styles.badge, styles.warn)}><AlertTriangle size={11} aria-hidden="true" />{lowResLabel}</span>
          )}
        </>
      ) : isPdf && pdfThumb ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={pdfThumb.dataUrl} alt="" className={styles.cover} />
          <span className={styles.badge}>{badge}</span>
        </>
      ) : (
        <div className={styles.textBody}>
          <span className={styles.name}>{file.name}</span>
          <span className={styles.meta}>
            {typeof lineCount === 'number' ? lineCountLabel(lineCount) : formatSize(file.size)}
          </span>
          <span className={styles.badge}>{badge}</span>
        </div>
      )}
      <button
        type="button"
        className={cx('composer-tile-remove', styles.remove)}
        onClick={onRemove}
        aria-label={removeLabel}
      >
        <X size={13} />
      </button>
    </div>
  );
}
