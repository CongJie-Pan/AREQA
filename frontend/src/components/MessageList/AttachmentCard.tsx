import { FileText, Image as ImageIcon } from 'lucide-react';
import type { AttachmentMetadata } from '@/database/schema';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { useStyles } from './styles';

function formatFileSize(sizeBytes: number): string | null {
  if (sizeBytes <= 0) return null;
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentCard({ attachment }: { attachment: AttachmentMetadata }) {
  const { styles } = useStyles();
  const { t } = useUserPreferences();
  const isImage = attachment.mediaType.startsWith('image/');
  const sizeLabel = formatFileSize(attachment.sizeBytes);

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
