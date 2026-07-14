import { ChevronDown, FileText, Image as ImageIcon, Paperclip } from 'lucide-react';
import { Popover } from 'antd';
import type { AttachmentMetadata } from '@/database/schema';
import { useStyles } from './styles';

export function AttachmentToggleList({
  attachments,
  expanded,
  listId,
  onExpandedChange,
}: {
  attachments: AttachmentMetadata[];
  expanded: boolean;
  listId: string;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const { styles, cx } = useStyles();

  const attachmentList = (
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
  );

  return (
    <div className={styles.messageAttachmentToggleWrap}>
      <Popover
        content={attachmentList}
        open={expanded}
        onOpenChange={onExpandedChange}
        trigger={['click']}
        placement="bottomRight"
        arrow={false}
        autoAdjustOverflow
        destroyOnHidden
        classNames={{ container: styles.messageAttachmentPopoverContainer }}
      >
        <button
          type="button"
          className={styles.messageAttachmentToggle}
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
      </Popover>
    </div>
  );
}
