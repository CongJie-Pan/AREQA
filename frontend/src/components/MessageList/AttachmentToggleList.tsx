import { ChevronDown, FileText, Image as ImageIcon, Paperclip } from 'lucide-react';
import type { AttachmentMetadata } from '@/database/schema';
import { useStyles } from './styles';

export function AttachmentToggleList({
  attachments,
  expanded,
  listId,
  onToggle,
}: {
  attachments: AttachmentMetadata[];
  expanded: boolean;
  listId: string;
  onToggle: () => void;
}) {
  const { styles, cx } = useStyles();

  return (
    <div className={styles.messageAttachmentToggleWrap}>
      <button
        type="button"
        className={styles.messageAttachmentToggle}
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={listId}
      >
        <span className={styles.messageAttachmentToggleIcon} aria-hidden="true">
          <Paperclip size={17} />
        </span>
        <span>{attachments.length} 個附件</span>
        <ChevronDown
          size={17}
          className={cx(styles.messageAttachmentToggleChevron, expanded && styles.messageAttachmentToggleChevronOpen)}
          aria-hidden="true"
        />
      </button>

      {expanded && (
        <div
          id={listId}
          className={styles.messageAttachmentDropdown}
          aria-label="附件檔名列表"
        >
          {attachments.map((attachment, index) => {
            const isImage = attachment.mediaType.startsWith('image/');
            return (
              <div
                className={styles.messageAttachmentDropdownItem}
                key={`${attachment.name}-${index}`}
                title={attachment.name}
              >
                <span className={styles.messageAttachmentDropdownIcon} aria-hidden="true">
                  {isImage ? <ImageIcon size={14} /> : <FileText size={14} />}
                </span>
                <span className={styles.messageAttachmentDropdownName}>{attachment.name}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
