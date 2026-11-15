import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, Download, FileText, Image as ImageIcon, X } from 'lucide-react';
import type { AttachmentMetadata } from '@/database/schema';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { renderPdfFirstPage } from '@/utils/attachmentPreview';
import { getSessionAttachment, getSessionAttachmentUrl } from '@/utils/attachmentSession';
import { useStyles } from './styles';

/** Longest edge for the larger first-page render shown inside the PDF dialog. */
const PDF_DIALOG_EDGE = 960;

function formatFileSize(sizeBytes: number): string | null {
  if (sizeBytes <= 0) return null;
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isPdfAttachment(attachment: AttachmentMetadata): boolean {
  return attachment.mediaType === 'application/pdf' || attachment.name.toLowerCase().endsWith('.pdf');
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);
}

/** Full-screen viewer shared with AI answer images (same lightbox styles). */
function AttachmentImageViewer({
  attachment, original, onClose,
}: { attachment: AttachmentMetadata; original?: File; onClose: () => void }) {
  const { styles } = useStyles();
  const { t } = useUserPreferences();
  const originalUrl = original ? getSessionAttachmentUrl(original) : '';
  useEscape(onClose);
  const src = originalUrl || attachment.preview?.dataUrl || '';

  return createPortal(
    <div
      className={styles.answerImageLightbox}
      role="dialog"
      aria-modal="true"
      aria-label={attachment.name}
      onClick={onClose}
    >
      <button type="button" className={styles.answerImageLightboxBack} aria-label={t('attachmentClosePreview')} onClick={onClose}>
        <ArrowLeft size={24} aria-hidden="true" />
      </button>
      {originalUrl && (
        <a
          href={originalUrl}
          download={attachment.name}
          aria-label={t('attachmentDownload')}
          title={t('attachmentDownload')}
          className={`${styles.answerImageLightboxClose} ${styles.answerImageLightboxDownload}`}
          onClick={(event) => event.stopPropagation()}
        >
          <Download size={20} aria-hidden="true" />
        </a>
      )}
      <button type="button" className={styles.answerImageLightboxClose} aria-label={t('attachmentClosePreview')} onClick={onClose}>
        <X size={20} aria-hidden="true" />
      </button>
      <div className={styles.answerImageLightboxStage} onClick={(event) => event.stopPropagation()}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={attachment.name} className={styles.answerImageLightboxImage} />
      </div>
      <div className={styles.answerImageLightboxMeta} onClick={(event) => event.stopPropagation()}>
        <p className={styles.answerImageLightboxCaption}>{attachment.name}</p>
        <div className={styles.answerImageLightboxSourceLine}>
          <span>{t('uploadedAttachmentBadge')}</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Compact dialog: file name, first-page preview and a download link. */
function AttachmentPdfDialog({
  attachment, original, onClose,
}: { attachment: AttachmentMetadata; original?: File; onClose: () => void }) {
  const { styles } = useStyles();
  const { t } = useUserPreferences();
  const originalUrl = original ? getSessionAttachmentUrl(original) : '';
  const [largePreview, setLargePreview] = useState('');
  useEscape(onClose);

  useEffect(() => {
    if (!original) return undefined;
    let active = true;
    // The stored thumbnail shows immediately; a sharper render replaces it.
    renderPdfFirstPage(original, PDF_DIALOG_EDGE, Number.POSITIVE_INFINITY)
      .then((preview) => { if (active && preview) setLargePreview(preview.dataUrl); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [original]);

  const src = largePreview || attachment.preview?.dataUrl || '';

  return createPortal(
    <div className={styles.attachmentDialogBackdrop} onClick={onClose}>
      <div
        className={styles.attachmentDialog}
        role="dialog"
        aria-modal="true"
        aria-label={attachment.name}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={styles.attachmentDialogHeader}>
          <h2 className={styles.attachmentDialogTitle} title={attachment.name}>{attachment.name}</h2>
          <button type="button" autoFocus className={styles.attachmentDialogClose} aria-label={t('attachmentClosePreview')} onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className={styles.attachmentDialogBody}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {src && <img src={src} alt={attachment.name} />}
          {originalUrl ? (
            <a className={styles.attachmentDialogDownload} href={originalUrl} download={attachment.name}>
              <Download size={16} aria-hidden="true" />
              {t('attachmentDownload')}
            </a>
          ) : (
            <p className={styles.attachmentDialogNote}>{t('attachmentOriginalUnavailable')}</p>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

/**
 * One uploaded attachment in a user message.
 *
 * With a stored thumbnail it renders as a clickable preview (images keep their
 * proportions when shown alone; PDFs and multi-file rows use square tiles).
 * Without one (older messages, other file types) it keeps the plain file card.
 */
export function AttachmentCard({
  attachment, messageId, index = 0, tile = false,
}: { attachment: AttachmentMetadata; messageId?: string; index?: number; tile?: boolean }) {
  const { styles, cx } = useStyles();
  const { t } = useUserPreferences();
  const [isOpen, setIsOpen] = useState(false);
  const isImage = attachment.mediaType.startsWith('image/');
  const isPdf = isPdfAttachment(attachment);
  const sizeLabel = formatFileSize(attachment.sizeBytes);
  const close = React.useCallback(() => setIsOpen(false), []);

  if (!attachment.preview || (!isImage && !isPdf)) {
    if (tile) {
      // In a multi-file gallery every file is a square tile: name plus type badge.
      const extension = /\.([A-Za-z0-9]{1,8})$/.exec(attachment.name)?.[1] ?? '';
      return (
        <div
          className={cx(styles.messageAttachmentThumbButton, styles.messageAttachmentTile, styles.messageAttachmentDocTile)}
          title={attachment.name}
          aria-label={t('attachmentItemLabel', { name: attachment.name })}
        >
          <span className={styles.messageAttachmentDocName}>{attachment.name}</span>
          <span className={styles.messageAttachmentTypeBadge} aria-hidden="true">
            {(isPdf ? 'pdf' : extension || 'file').toUpperCase()}
          </span>
        </div>
      );
    }
    return (
      <div
        className={styles.messageAttachmentCard}
        title={attachment.name}
        aria-label={t('attachmentItemLabel', { name: attachment.name })}
      >
        <span className={styles.messageAttachmentIcon} aria-hidden="true">
          {isImage ? <ImageIcon size={17} /> : <FileText size={17} />}
        </span>
        <span className={styles.messageAttachmentDetails}>
          <span className={styles.messageAttachmentName}>{attachment.name}</span>
          {sizeLabel && <span className={styles.messageAttachmentMeta}>{sizeLabel}</span>}
        </span>
      </div>
    );
  }

  const original = isOpen && messageId ? getSessionAttachment(messageId, index) : undefined;
  const useTile = tile || isPdf;

  return (
    <>
      <button
        type="button"
        className={cx(
          styles.messageAttachmentThumbButton,
          useTile ? styles.messageAttachmentTile : styles.messageAttachmentImageSingle,
        )}
        title={attachment.name}
        aria-label={t('attachmentOpenPreview', { name: attachment.name })}
        aria-haspopup="dialog"
        onClick={() => setIsOpen(true)}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={attachment.preview.dataUrl}
          alt=""
          width={attachment.preview.width}
          height={attachment.preview.height}
          loading="lazy"
          decoding="async"
        />
        {isPdf && <span className={styles.messageAttachmentTypeBadge} aria-hidden="true">PDF</span>}
      </button>
      {isOpen && (isPdf
        ? <AttachmentPdfDialog attachment={attachment} original={original} onClose={close} />
        : <AttachmentImageViewer attachment={attachment} original={original} onClose={close} />)}
    </>
  );
}

/**
 * The attachments above a sent message: images first, then documents on their
 * own bottom row, so many files still read top-to-bottom in a clear order.
 * Original indexes are kept because session originals are looked up by index.
 */
export function AttachmentGallery({ attachments, messageId }: { attachments: AttachmentMetadata[]; messageId: string }) {
  const { styles } = useStyles();
  const indexed = attachments.map((attachment, index) => ({ attachment, index }));
  const images = indexed.filter(({ attachment }) => attachment.mediaType.startsWith('image/'));
  const documents = indexed.filter(({ attachment }) => !attachment.mediaType.startsWith('image/'));
  const tile = attachments.length > 1;
  const row = (items: typeof indexed) => (
    <div className={styles.messageAttachmentGallery}>
      {items.map(({ attachment, index }) => (
        <AttachmentCard
          key={`${attachment.name}-${index}`}
          attachment={attachment}
          messageId={messageId}
          index={index}
          tile={tile}
        />
      ))}
    </div>
  );

  return (
    <div className={styles.messageAttachmentGalleryGroups}>
      {images.length > 0 && row(images)}
      {documents.length > 0 && row(documents)}
    </div>
  );
}
